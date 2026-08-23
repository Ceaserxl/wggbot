from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any
from urllib.parse import urlparse

import aiohttp
import yt_dlp

from core.settings import Settings

from .models import Track

LOGGER = logging.getLogger(__name__)


class MediaResolutionError(RuntimeError):
    pass


class MediaResolver:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._extract_limit = asyncio.Semaphore(3)
        self._session: aiohttp.ClientSession | None = None
        self._spotify_token: str | None = None

    @property
    def cookie_available(self) -> bool:
        path = self.settings.ytdlp_cookie_file
        return bool(path and path.is_file())

    def _ydl_options(self, *, playlist: bool, playlist_limit: int | None = None) -> dict[str, Any]:
        options: dict[str, Any] = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": not playlist,
            "default_search": "ytsearch1",
            "socket_timeout": 20,
            "retries": 3,
        }
        if playlist:
            options["extract_flat"] = "in_playlist"
            options["playlistend"] = playlist_limit
        if self.cookie_available:
            options["cookiefile"] = str(self.settings.ytdlp_cookie_file)
        return options

    async def resolve(
        self,
        query: str,
        requester_id: int,
        requester_mention: str,
        playlist_limit: int,
    ) -> list[Track]:
        query = query.strip()
        if not query:
            raise MediaResolutionError("Enter a URL or search query.")
        if self._is_spotify_url(query):
            return await self._resolve_spotify(
                query, requester_id, requester_mention, playlist_limit
            )
        return await self._resolve_ytdlp(query, requester_id, requester_mention, playlist_limit)

    @staticmethod
    def _is_spotify_url(value: str) -> bool:
        try:
            return urlparse(value).hostname in {"open.spotify.com", "www.open.spotify.com"}
        except ValueError:
            return False

    async def _resolve_ytdlp(
        self,
        query: str,
        requester_id: int,
        requester_mention: str,
        playlist_limit: int,
    ) -> list[Track]:
        async with self._extract_limit:
            try:
                info = await asyncio.to_thread(self._extract, query, True, playlist_limit)
            except yt_dlp.utils.DownloadError as exc:
                LOGGER.info("Media lookup failed for %r: %s", query, exc)
                raise MediaResolutionError("That media could not be resolved.") from exc

        entries = list(info.get("entries") or []) if info else []
        if not entries and info:
            entries = [info]
        tracks = [
            self._track_from_info(entry, requester_id, requester_mention)
            for entry in entries[:playlist_limit]
            if entry
        ]
        tracks = [track for track in tracks if track.webpage_url]
        if not tracks:
            raise MediaResolutionError("No playable tracks were found.")
        return tracks

    def _extract(
        self, query: str, playlist: bool, playlist_limit: int | None = None
    ) -> dict[str, Any]:
        with yt_dlp.YoutubeDL(
            self._ydl_options(playlist=playlist, playlist_limit=playlist_limit)
        ) as ydl:
            result = ydl.extract_info(query, download=False)
        return result or {}

    @staticmethod
    def _track_from_info(info: dict[str, Any], requester_id: int, requester_mention: str) -> Track:
        extractor = str(info.get("extractor_key") or info.get("extractor") or "media")
        webpage_url = str(info.get("webpage_url") or info.get("original_url") or "")
        if not webpage_url:
            raw_url = str(info.get("url") or "")
            video_id = str(info.get("id") or "")
            if "youtube" in extractor.lower() and video_id:
                webpage_url = f"https://www.youtube.com/watch?v={video_id}"
            elif raw_url.startswith(("http://", "https://", "ytsearch")):
                webpage_url = raw_url
        artists = info.get("artists") or []
        artist = (
            info.get("artist")
            or (artists[0] if artists and isinstance(artists[0], str) else None)
            or info.get("uploader")
            or info.get("channel")
            or "Unknown artist"
        )
        duration = info.get("duration")
        return Track(
            title=str(info.get("track") or info.get("title") or "Unknown title"),
            artist=str(artist),
            webpage_url=webpage_url,
            original_url=webpage_url,
            requester_id=requester_id,
            requester_mention=requester_mention,
            duration=int(duration) if isinstance(duration, int | float) else None,
            source=extractor,
            thumbnail=info.get("thumbnail"),
        )

    async def stream_url(self, track: Track) -> str:
        async with self._extract_limit:
            try:
                info = await asyncio.to_thread(self._extract, track.webpage_url, False)
            except yt_dlp.utils.DownloadError as exc:
                raise MediaResolutionError(f"Could not open {track.title}.") from exc
        entries = list(info.get("entries") or [])
        if entries:
            info = entries[0] or {}
        formats = info.get("formats") or []
        audio_url = info.get("url")
        if not audio_url:
            audio_url = next(
                (
                    item.get("url")
                    for item in reversed(formats)
                    if item.get("acodec") != "none" and item.get("url")
                ),
                None,
            )
        if not audio_url:
            raise MediaResolutionError(f"No audio stream is available for {track.title}.")
        return str(audio_url)

    async def _session_for_api(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        return self._session

    async def _spotify_access_token(self) -> str:
        if self._spotify_token:
            return self._spotify_token
        client_id = self.settings.spotify_client_id
        client_secret = self.settings.spotify_client_secret
        if not client_id or not client_secret:
            raise MediaResolutionError(
                "Spotify links require SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET. "
                "Direct URLs and searches remain available."
            )
        raw = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        session = await self._session_for_api()
        async with session.post(
            "https://accounts.spotify.com/api/token",
            data={"grant_type": "client_credentials"},
            headers={"Authorization": f"Basic {raw}"},
        ) as response:
            if response.status != 200:
                raise MediaResolutionError("Spotify authentication failed.")
            data = await response.json()
        self._spotify_token = str(data["access_token"])
        return self._spotify_token

    async def _spotify_get(self, endpoint: str, retry: bool = True) -> dict[str, Any]:
        session = await self._session_for_api()
        token = await self._spotify_access_token()
        async with session.get(
            f"https://api.spotify.com/v1/{endpoint.lstrip('/')}",
            headers={"Authorization": f"Bearer {token}"},
        ) as response:
            status = response.status
            data = await response.json() if status == 200 else {}
        if status == 401 and retry:
            self._spotify_token = None
            return await self._spotify_get(endpoint, retry=False)
        if status != 200:
            raise MediaResolutionError(f"Spotify returned HTTP {status}.")
        return data

    async def _spotify_collection(self, endpoint: str, limit: int) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        offset = 0
        while len(items) < limit:
            page_size = min(50, limit - len(items))
            separator = "&" if "?" in endpoint else "?"
            data = await self._spotify_get(
                f"{endpoint}{separator}limit={page_size}&offset={offset}"
            )
            page = [item for item in data.get("items", []) if isinstance(item, dict)]
            items.extend(page)
            if len(page) < page_size or not data.get("next"):
                break
            offset += len(page)
        return items[:limit]

    async def _resolve_spotify(
        self,
        url: str,
        requester_id: int,
        requester_mention: str,
        playlist_limit: int,
    ) -> list[Track]:
        parts = [part for part in urlparse(url).path.split("/") if part]
        if len(parts) < 2 or parts[-2] not in {"track", "album", "playlist"}:
            raise MediaResolutionError("Unsupported Spotify URL.")
        kind, item_id = parts[-2], parts[-1]
        if kind == "track":
            raw_tracks = [await self._spotify_get(f"tracks/{item_id}")]
        elif kind == "album":
            raw_tracks = await self._spotify_collection(f"albums/{item_id}/tracks", playlist_limit)
        else:
            raw_items = await self._spotify_collection(f"playlists/{item_id}/items", playlist_limit)
            raw_tracks = []
            for item in raw_items:
                candidate = item.get("item")
                if isinstance(candidate, dict):
                    raw_tracks.append(candidate)

        tracks = []
        for item in raw_tracks[:playlist_limit]:
            if not isinstance(item, dict):
                continue
            artists = ", ".join(artist.get("name", "") for artist in item.get("artists", []))
            title = str(item.get("name") or "Unknown title")
            tracks.append(
                Track(
                    title=title,
                    artist=artists or "Unknown artist",
                    webpage_url=f"ytsearch1:{artists} - {title} official audio",
                    original_url=url,
                    requester_id=requester_id,
                    requester_mention=requester_mention,
                    duration=int(item.get("duration_ms", 0) / 1000) or None,
                    source="Spotify metadata → media search",
                )
            )
        if not tracks:
            raise MediaResolutionError("Spotify returned no playable track metadata.")
        return tracks

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
