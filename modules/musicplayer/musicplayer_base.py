# /app/modules/musicplayer/musicplayer_base.py

import asyncio
import re
import os
import sys
import shutil
import discord
import yt_dlp as youtube_dl
from pathlib import Path

from core.logging import log, sublog


# ============================================================
# Configuration
# ============================================================
COOKIES_FILE = "cookies.txt"


# ============================================================
# State Stores
# ============================================================
queues = {}
currently_playing = {}
disconnect_requested = {}
current_song = {}


# ============================================================
# Queue Helpers
# ============================================================
def get_queue(guild_id):
    if guild_id not in queues:
        log(f"[queue] Creating new queue for guild {guild_id}")
        queues[guild_id] = asyncio.Queue()
    return queues[guild_id]


def strip_playlist(url: str) -> str:
    """Remove playlist portion to force single-track extraction."""
    cleaned = re.sub(r'(\?|&)list=[^&]*', '', url)
    if cleaned != url:
        log(f"[url] Playlist stripped → {cleaned}")
    return cleaned


# ============================================================
# yt-dlp Config
# ============================================================
def ydl_basic():
    return {
        "format": "bestaudio/best",
        "quiet": True,
        "cookies": COOKIES_FILE,
        "skip_download": True,
        "noplaylist": True,
        "extractor_args": {"youtube": {"player_client": ["android"]}},
    }


def ydl_playlist(items):
    return {
        "quiet": True,
        "cookies": COOKIES_FILE,
        "extract_flat": True,
        "playlist_items": items,
        "skip_download": True,
        "extractor_args": {"youtube": {"player_client": ["android"]}},
    }


# ============================================================
# Metadata Helpers
# ============================================================
def extract_artist(info):
    return (
        info.get("artist")
        or (info.get("artists")[0]["name"] if isinstance(info.get("artists"), list) else None)
        or info.get("album_artist")
        or info.get("uploader")
        or info.get("channel")
        or "Unknown Artist"
    )


def extract_audio_url(info):
    if "url" in info:
        return info["url"]

    for f in info.get("formats") or []:
        if f.get("acodec") != "none" and f.get("url"):
            return f["url"]

    return None


def find_ffmpeg():
    """Cross-platform FFmpeg resolution."""
    if os.name == "nt":
        local = Path(__file__).parent / "ffmpeg" / "ffmpeg.exe"
        if local.exists():
            log("[ffmpeg] Using local ffmpeg.exe")
            return str(local)

        exe = Path(sys.executable).with_name("ffmpeg.exe")
        if exe.exists():
            log("[ffmpeg] Using Python-adjacent ffmpeg.exe")
            return str(exe)

        which = shutil.which("ffmpeg.exe")
        if which:
            log("[ffmpeg] Using system ffmpeg.exe")
            return which

        log("[ffmpeg] No ffmpeg.exe found; defaulting to name only")
        return "ffmpeg.exe"

    which = shutil.which("ffmpeg")
    if which:
        log("[ffmpeg] Using system ffmpeg")
        return which
    log("[ffmpeg] No ffmpeg found; defaulting to name only")
    return "ffmpeg"


async def extract_title_artist(url: str):
    log(f"[meta] Extracting metadata for: {url}")
    with youtube_dl.YoutubeDL(ydl_basic()) as ydl:
        info = ydl.extract_info(url, download=False)
        title = info.get("track") or info.get("title") or "Unknown Title"
        artist = extract_artist(info)
        sublog(f"Metadata → {title} — {artist}")
        return title, artist


# ============================================================
# Core Playback
# ============================================================
async def play_audio(vc, url, mention, text_channel, title, artist):
    log(f"[play] Starting playback for {title} — {artist}")

    with youtube_dl.YoutubeDL(ydl_basic()) as ydl:
        info = ydl.extract_info(url, download=False)
        audio = extract_audio_url(info)

    if not audio:
        log(f"[ERR] Audio stream missing for {url}")
        await text_channel.send("❌ Could not find an audio stream.")
        return

    ffmpeg = find_ffmpeg()
    opts = {
        "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
        "options": '-vn -af "volume=0.07"',
    }

    vc.play(discord.FFmpegPCMAudio(executable=ffmpeg, source=audio, **opts))
    sublog(f"Playback started via FFmpeg")


# ============================================================
# Queue Processing
# ============================================================
async def play_next(interaction, queue):
    guild_id = interaction.guild_id

    if queue.empty():
        log(f"[queue] Guild {guild_id} queue finished")
        currently_playing[guild_id] = False
        current_song[guild_id] = None
        await interaction.followup.send("Queue finished.")
        return

    log(f"[queue] Fetching next track for guild {guild_id}")

    channel, url, mention, text_ch, title, artist = await queue.get()
    current_song[guild_id] = (channel, url, mention, text_ch, title, artist)

    vc = channel.guild.voice_client or await channel.connect()
    await play_audio(vc, url, mention, text_ch, title, artist)

    await interaction.followup.send(f"🎶 Now playing **{title}** — {artist}")

    while vc.is_playing():
        await asyncio.sleep(1)

    log(f"[queue] Finished track: {title}")
    currently_playing[guild_id] = False
    current_song[guild_id] = None

    await process_queue(interaction)


async def process_queue(interaction):
    guild_id = interaction.guild_id
    queue = get_queue(guild_id)
    log(f"[queue] Processing queue (size={queue.qsize()})")

    while not queue.empty() and not disconnect_requested.get(guild_id):
        channel, url, mention, text_ch, title, artist = await queue.get()

        log(f"[queue] Playing queued track: {title} — {artist}")

        currently_playing[guild_id] = True
        current_song[guild_id] = (channel, url, mention, text_ch, title, artist)

        vc = channel.guild.voice_client or await channel.connect()
        await play_audio(vc, url, mention, text_ch, title, artist)

        while vc.is_playing():
            await asyncio.sleep(1)

    log(f"[queue] Done processing queue for guild {guild_id}")
    currently_playing[guild_id] = False
    current_song[guild_id] = None


# ============================================================
# Public Command Logic
# ============================================================
async def handle_play(interaction, url, msg):
    guild_id = interaction.guild_id
    queue = get_queue(guild_id)
    disconnect_requested[guild_id] = False

    url = strip_playlist(url)

    if not interaction.user.voice:
        return await msg.edit(content="❌ You must be in a voice channel.")

    channel = interaction.user.voice.channel
    log(f"[play] User requested: {url} in {channel}")

    try:
        title, artist = await extract_title_artist(url)
    except Exception as e:
        log(f"[ERR] Metadata extraction failed: {e}")
        return await msg.edit(content=f"❌ Error: {e}")

    await msg.edit(content="Joining voice channel...")

    await queue.put((channel, url, interaction.user.mention, interaction.channel, title, artist))
    log(f"[queue] Added track to queue: {title}")

    if currently_playing.get(guild_id):
        await msg.edit(content=f"Added **{title}** to the queue.")
    else:
        await msg.edit(content=f"🎶 Now playing **{title}**")
        await process_queue(interaction)


async def handle_playlist(interaction, url, songs, msg):
    guild_id = interaction.guild_id
    queue = get_queue(guild_id)
    disconnect_requested[guild_id] = False

    if "list=" not in url:
        return await msg.edit(content="❌ This is not a playlist URL.")

    if not interaction.user.voice:
        return await msg.edit(content="❌ You must be in a voice channel.")

    log(f"[playlist] Reading playlist: {url} ({songs} tracks)")
    await msg.edit(content=f"Fetching playlist… first {songs} tracks.")

    try:
        with youtube_dl.YoutubeDL(ydl_playlist(f"1-{songs}")) as ydl:
            data = ydl.extract_info(url, download=False)
            entries = data.get("entries") or []
    except Exception as e:
        log(f"[ERR] Playlist load failed: {e}")
        return await msg.edit(content=f"❌ Playlist error: {e}")

    if not entries:
        log("[playlist] Playlist has no entries")
        return await msg.edit(content="❌ Playlist is empty.")

    log(f"[playlist] Adding {len(entries)} tracks")
    songs_to_add = []

    for entry in entries:
        vid = entry.get("id")
        if not vid:
            continue

        song_url = f"https://www.youtube.com/watch?v={vid}"
        title = entry.get("title", "Unknown Title")
        artist = entry.get("uploader", "Unknown Artist")

        songs_to_add.append((
            interaction.user.voice.channel,
            song_url,
            interaction.user.mention,
            interaction.channel,
            title,
            artist
        ))

    for s in songs_to_add:
        await queue.put(s)

    if currently_playing.get(guild_id):
        return await msg.edit(content="Playlist added to the queue.")

    first = songs_to_add[0]
    await msg.edit(content=f"🎶 Now playing **{first[4]}** — {first[5]}")
    await process_queue(interaction)


async def handle_queue(interaction):
    guild_id = interaction.guild_id
    queue = get_queue(guild_id)

    if queue.empty() and not currently_playing.get(guild_id):
        log(f"[queue] Queue is empty for guild {guild_id}")
        return await interaction.followup.send("Queue is empty.")

    txt = ""

    if current_song.get(guild_id):
        _, _, mention, _, title, artist = current_song[guild_id]
        txt += f"▶️ **Now Playing:** {title} — {artist} (requested by {mention})\n\n"

    items = list(queue._queue)
    for i, (_, _, mention, _, title, artist) in enumerate(items, start=1):
        txt += f"{i}. {title} — {artist} (requested by {mention})\n"

    log(f"[queue] Queried queue ({len(items)} upcoming tracks)")
    await interaction.followup.send(txt)


async def handle_disconnect(interaction):
    guild_id = interaction.guild_id
    queue = get_queue(guild_id)

    vc = interaction.guild.voice_client
    if not vc:
        log(f"[disconnect] Bot not in voice in guild {guild_id}")
        return await interaction.followup.send("Bot is not in a voice channel.")

    log(f"[disconnect] Disconnecting from guild {guild_id}")
    disconnect_requested[guild_id] = True

    await vc.disconnect()

    while not queue.empty():
        queue.get_nowait()

    currently_playing[guild_id] = False
    current_song[guild_id] = None

    await interaction.followup.send("🛑 Disconnected and cleared queue.")


async def handle_skip(interaction):
    guild_id = interaction.guild_id
    queue = get_queue(guild_id)

    vc = interaction.guild.voice_client
    if not vc or not vc.is_playing():
        log(f"[skip] No active playback in guild {guild_id}")
        return await interaction.followup.send("Nothing is currently playing.")

    log(f"[skip] User skipped track")
    vc.stop()
    await play_next(interaction, queue)
