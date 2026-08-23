from __future__ import annotations

import math
import re
from collections.abc import Sequence
from typing import TYPE_CHECKING

import discord

from .models import Track

if TYPE_CHECKING:
    from .player import GuildPlayer

PURPLE = discord.Color(0x8B5CF6)
GREEN = discord.Color(0x22C55E)
RED = discord.Color(0xEF4444)
SLATE = discord.Color(0x64748B)
QUEUE_PAGE_SIZE = 8


def _trim(value: str, length: int) -> str:
    return value if len(value) <= length else value[: length - 1].rstrip() + "…"


def _safe(value: str, length: int = 90) -> str:
    return re.sub(r"([\\*_`~|>])", r"\\\1", _trim(value, length))


def _track_link(track: Track, *, include_artist: bool = False) -> str:
    label = track.label if include_artist else track.title
    escaped = _safe(label)
    return f"[{escaped}]({track.link_url})" if track.link_url else f"**{escaped}**"


def _loop_label(mode: str) -> str:
    return {"off": "Off", "one": "Track", "all": "Queue"}.get(mode, "Off")


def _state_label(state: str) -> str:
    return {"playing": "Playing", "paused": "Paused", "idle": "Idle"}.get(state, state.title())


def _total_duration(tracks: Sequence[Track]) -> str:
    known = sum(track.duration or 0 for track in tracks)
    if known <= 0:
        return "—"
    minutes, seconds = divmod(known, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m" if hours else f"{minutes}m {seconds:02d}s"


def now_playing_embed(player: GuildPlayer) -> discord.Embed:
    track = player.current
    if track is None:
        return status_embed("Playback finished", "The queue has reached its end.", color=SLATE)

    state = _state_label(player.playback_state)
    icon = "⏸" if player.playback_state == "paused" else "▶"
    embed = discord.Embed(
        title=_safe(track.title, 200),
        description=f"### {_safe(track.artist, 120)}\n{icon} **{state}**",
        color=PURPLE,
        url=track.link_url,
    )
    embed.set_author(name="WGGBot Music  •  Now playing")
    embed.add_field(name="Duration", value=f"`{track.duration_label}`", inline=True)
    embed.add_field(name="Volume", value=f"`{round(player.volume * 100)}%`", inline=True)
    embed.add_field(name="Up next", value=f"`{len(player.queue)} tracks`", inline=True)
    embed.add_field(name="Loop", value=f"`{_loop_label(player.repeat_mode)}`", inline=True)
    embed.add_field(name="Requested by", value=track.requester_mention, inline=True)
    embed.add_field(name="Source", value=f"`{_safe(track.source, 32)}`", inline=True)
    if track.thumbnail and track.thumbnail.startswith(("https://", "http://")):
        embed.set_thumbnail(url=track.thumbnail)
    embed.set_footer(text="Use the controls below • /music queue opens the full queue")
    return embed


def queue_embed(
    player: GuildPlayer,
    page: int = 0,
    per_page: int = QUEUE_PAGE_SIZE,
) -> tuple[discord.Embed, int, int]:
    tracks = list(player.queue)
    pages = max(1, math.ceil(len(tracks) / per_page))
    page = min(max(0, page), pages - 1)
    start = page * per_page
    visible = tracks[start : start + per_page]

    if player.current:
        current = (
            f"**Now playing**\n{_track_link(player.current, include_artist=True)} "
            f"`{player.current.duration_label}`"
        )
    else:
        current = "**Now playing**\nNothing right now"

    if visible:
        rows = []
        for index, track in enumerate(visible, start + 1):
            rows.append(
                f"**`{index:02d}`**  {_track_link(track)}  `{track.duration_label}`\n"
                f"> {_safe(track.artist, 60)}  •  {track.requester_mention}"
            )
        listing = "\n\n".join(rows)
    else:
        listing = "*No upcoming tracks. Add one with `/music play`."

    embed = discord.Embed(
        title="Music queue",
        description=f"{current}\n\n{listing}",
        color=PURPLE if player.current or tracks else SLATE,
    )
    embed.set_author(name="WGGBot Music  •  Queue")
    embed.add_field(name="Tracks", value=f"`{len(tracks)}`", inline=True)
    embed.add_field(name="Runtime", value=f"`{_total_duration(tracks)}`", inline=True)
    embed.add_field(name="Page", value=f"`{page + 1} / {pages}`", inline=True)
    embed.set_footer(text="Browse pages or manage playback with the controls below")
    return embed, page, pages


def queued_embed(tracks: Sequence[Track], queue_size: int) -> discord.Embed:
    count = len(tracks)
    headline = f"{count} track{'s' if count != 1 else ''} added"
    preview = "\n".join(
        f"**`{index:02d}`**  {_track_link(track, include_artist=True)}  `{track.duration_label}`"
        for index, track in enumerate(tracks[:4], 1)
    )
    if count > 4:
        preview += f"\n*…and {count - 4} more*"
    embed = discord.Embed(title=headline, description=preview, color=GREEN)
    embed.set_author(name="WGGBot Music  •  Added to queue")
    embed.add_field(name="Queue size", value=f"`{queue_size}`", inline=True)
    embed.add_field(name="Added runtime", value=f"`{_total_duration(tracks)}`", inline=True)
    embed.set_footer(text="Use the page controls below to browse the full queue")
    if (
        count == 1
        and tracks[0].thumbnail
        and tracks[0].thumbnail.startswith(("https://", "http://"))
    ):
        embed.set_thumbnail(url=tracks[0].thumbnail)
    return embed


def history_embed(tracks: Sequence[Track]) -> discord.Embed:
    rows = "\n".join(
        f"**`{index:02d}`**  {_track_link(track, include_artist=True)}"
        for index, track in enumerate(tracks, 1)
    )
    embed = discord.Embed(title="Recently played", description=rows, color=PURPLE)
    embed.set_author(name="WGGBot Music  •  History")
    embed.set_footer(text=f"Showing the latest {len(tracks)} tracks")
    return embed


def sources_embed(*, cookies: bool, spotify: bool) -> discord.Embed:
    ready = "🟢 Ready"
    embed = discord.Embed(
        title="Playback sources",
        description="Search and all yt-dlp-supported media URLs are ready.",
        color=GREEN,
    )
    embed.set_author(name="WGGBot Music  •  Source status")
    embed.add_field(name="Media search", value=ready, inline=False)
    embed.add_field(
        name="YouTube account",
        value=ready if cookies else "⚪ Cookie not mounted",
        inline=False,
    )
    embed.add_field(
        name="Spotify matching",
        value=ready if spotify else "⚪ Credentials not configured",
        inline=False,
    )
    return embed


def status_embed(
    title: str,
    description: str,
    *,
    success: bool = False,
    error: bool = False,
    color: discord.Color | None = None,
) -> discord.Embed:
    if color is None:
        color = RED if error else GREEN if success else PURPLE
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_author(name="WGGBot Music")
    return embed
