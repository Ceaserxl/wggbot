from __future__ import annotations

import asyncio
import logging
import random
from collections import deque
from collections.abc import Awaitable, Callable
from typing import cast

import discord

from ..settings import Settings
from .models import Track
from .presentation import status_embed
from .resolver import MediaResolutionError, MediaResolver

LOGGER = logging.getLogger(__name__)
TrackStartHandler = Callable[["GuildPlayer", Track], Awaitable[None]]


class QueueFullError(RuntimeError):
    pass


class GuildPlayer:
    def __init__(
        self,
        guild_id: int,
        resolver: MediaResolver,
        settings: Settings,
        on_track_start: TrackStartHandler | None = None,
    ) -> None:
        self.guild_id = guild_id
        self.resolver = resolver
        self.settings = settings
        self.on_track_start = on_track_start
        self.queue: deque[Track] = deque()
        self.history: deque[Track] = deque(maxlen=25)
        self.current: Track | None = None
        self.voice_channel: discord.VoiceChannel | discord.StageChannel | None = None
        self.text_channel: discord.abc.Messageable | None = None
        self.voice_client: discord.VoiceClient | None = None
        self.volume = settings.music_default_volume / 100
        self.repeat_mode = "off"
        self._wake = asyncio.Event()
        self._closed = False
        self._skip_requested = False
        self._connect_lock = asyncio.Lock()
        self._worker = asyncio.create_task(self._run(), name=f"music-player-{guild_id}")

    @property
    def playback_state(self) -> str:
        if self.voice_client and self.voice_client.is_paused():
            return "paused"
        if self.current is not None:
            return "playing"
        return "idle"

    def enqueue(self, tracks: list[Track]) -> None:
        if len(self.queue) + len(tracks) > self.settings.music_max_queue:
            raise QueueFullError(
                f"The queue limit is {self.settings.music_max_queue}; "
                f"only {self.settings.music_max_queue - len(self.queue)} slots remain."
            )
        self.queue.extend(tracks)
        self._wake.set()

    def bind(
        self,
        voice_channel: discord.VoiceChannel | discord.StageChannel,
        text_channel: discord.abc.Messageable,
    ) -> None:
        self.voice_channel = voice_channel
        self.text_channel = text_channel
        self._wake.set()

    async def _connect(self) -> discord.VoiceClient:
        if self.voice_channel is None:
            raise RuntimeError("No voice channel is selected.")
        async with self._connect_lock:
            guild_client = self.voice_channel.guild.voice_client
            voice_client = cast(discord.VoiceClient | None, guild_client)
            if voice_client and voice_client.is_connected():
                if voice_client.channel != self.voice_channel:
                    await voice_client.move_to(self.voice_channel)
                self.voice_client = voice_client
            else:
                self.voice_client = cast(
                    discord.VoiceClient, await self.voice_channel.connect(reconnect=True)
                )
            return self.voice_client

    async def _run(self) -> None:
        try:
            while not self._closed:
                if not self.queue:
                    self._wake.clear()
                    try:
                        await asyncio.wait_for(
                            self._wake.wait(), timeout=self.settings.music_idle_timeout
                        )
                    except TimeoutError:
                        await self.disconnect(clear=False)
                    continue

                track = self.queue.popleft()
                self.current = track
                self._skip_requested = False
                try:
                    await self._play(track)
                except (MediaResolutionError, discord.DiscordException, OSError, RuntimeError):
                    LOGGER.exception("Playback failed in guild %s", self.guild_id)
                    await self._notify_failure(track)
                finally:
                    self.history.appendleft(track)
                    self.current = None

                if not self._skip_requested:
                    if self.repeat_mode == "one":
                        self.queue.appendleft(track)
                    elif self.repeat_mode == "all":
                        self.queue.append(track)
        except asyncio.CancelledError:
            raise
        finally:
            if self.voice_client and self.voice_client.is_connected():
                await self.voice_client.disconnect(force=True)

    async def _play(self, track: Track) -> None:
        voice = await self._connect()
        stream = await self.resolver.stream_url(track)
        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(
                stream,
                before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                options="-vn",
            ),
            volume=self.volume,
        )
        loop = asyncio.get_running_loop()
        finished = asyncio.Event()
        playback_error: list[Exception] = []

        def after(error: Exception | None) -> None:
            if error:
                playback_error.append(error)
            loop.call_soon_threadsafe(finished.set)

        voice.play(source, after=after)
        if self.on_track_start is not None:
            await self.on_track_start(self, track)
        await finished.wait()
        if playback_error:
            raise RuntimeError(str(playback_error[0]))

    async def _notify_failure(self, track: Track) -> None:
        if self.text_channel:
            await self.text_channel.send(
                embed=status_embed(
                    "Track unavailable",
                    f"Could not play **{track.label}**. Moving to the next track.",
                    error=True,
                ),
                allowed_mentions=discord.AllowedMentions.none(),
            )

    def pause(self) -> bool:
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()
            return True
        return False

    def resume(self) -> bool:
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()
            return True
        return False

    def skip(self) -> bool:
        if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
            self._skip_requested = True
            self.voice_client.stop()
            return True
        return False

    def clear(self) -> int:
        count = len(self.queue)
        self.queue.clear()
        return count

    def remove(self, position: int) -> Track:
        if position < 1 or position > len(self.queue):
            raise IndexError("Queue position is out of range.")
        items = list(self.queue)
        track = items.pop(position - 1)
        self.queue = deque(items)
        return track

    def move(self, source: int, destination: int) -> Track:
        if (
            source < 1
            or source > len(self.queue)
            or destination < 1
            or destination > len(self.queue)
        ):
            raise IndexError("Queue position is out of range.")
        items = list(self.queue)
        track = items.pop(source - 1)
        items.insert(destination - 1, track)
        self.queue = deque(items)
        return track

    def shuffle(self) -> int:
        items = list(self.queue)
        random.SystemRandom().shuffle(items)
        self.queue = deque(items)
        return len(items)

    def set_volume(self, percent: int) -> None:
        self.volume = percent / 100
        if self.voice_client and isinstance(self.voice_client.source, discord.PCMVolumeTransformer):
            self.voice_client.source.volume = self.volume

    async def disconnect(self, *, clear: bool = True) -> None:
        if clear:
            self.queue.clear()
        self._skip_requested = True
        if self.voice_client:
            if self.voice_client.is_playing() or self.voice_client.is_paused():
                self.voice_client.stop()
            if self.voice_client.is_connected():
                await self.voice_client.disconnect(force=True)
        self.voice_client = None

    async def close(self) -> None:
        self._closed = True
        self._wake.set()
        await self.disconnect()
        self._worker.cancel()
        await asyncio.gather(self._worker, return_exceptions=True)
