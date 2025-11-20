# resources/music_handling.py

# ── Imports ─────────────────────────────────────────────────────────────
import asyncio
import re
import os
import sys
import shutil
from pathlib import Path

import discord
import yt_dlp as youtube_dl

# ── Config ──────────────────────────────────────────────────────────────
COOKIES_FILE = "cookies.txt"

# ── State Storage ───────────────────────────────────────────────────────
queues = {}
currently_playing = {}
disconnect_requested = {}
current_song = {}

# ── Queue Utilities ─────────────────────────────────────────────────────
def get_guild_queue(guild_id):
    if guild_id not in queues:
        queues[guild_id] = asyncio.Queue()
    return queues[guild_id]


def strip_youtube_playlist(url: str) -> str:
    """Strip ?list= to force single-video mode."""
    return re.sub(r'(\?|&)list=[^&]*', '', url)


# ── yt-dlp Helpers ──────────────────────────────────────────────────────
def build_ydl_opts_basic():
    """Options for single video or single YouTube Music track."""
    return {
        "format": "bestaudio/best",
        "quiet": True,
        "cookies": COOKIES_FILE,
        "skip_download": True,
        "noplaylist": True,

        # 🔥 Required to avoid SABR fallback
        "extractor_args": {
            "youtube": {
                "player_client": ["android"],
            }
        },
    }


def build_ydl_opts_playlist(items: str):
    """Options for playlist-only metadata extraction."""
    return {
        "quiet": True,
        "cookies": COOKIES_FILE,
        "extract_flat": True,
        "playlist_items": items,
        "skip_download": True,

        # Prevent SABR on playlists too
        "extractor_args": {
            "youtube": {
                "player_client": ["android"],
            }
        },
    }


def extract_artist(info):
    """Try multiple metadata fields to support YouTube & YouTube Music."""
    return (
        info.get("artist")
        or (info.get("artists")[0]["name"] if isinstance(info.get("artists"), list) and info.get("artists") else None)
        or info.get("album_artist")
        or info.get("uploader")
        or info.get("channel")
        or "Unknown Artist"
    )


def extract_audio_url(info):
    """Extract a playable audio URL from yt-dlp info dict."""
    if "url" in info:
        return info["url"]

    formats = info.get("formats") or []
    for f in formats:
        if f.get("acodec") != "none" and f.get("url"):
            return f["url"]

    return None


def resolve_ffmpeg_executable():
    """Locate usable ffmpeg binary."""
    if os.name == "nt":
        exe = Path(sys.executable).with_name("ffmpeg.exe")
        if not exe.exists():
            alt = Path(__file__).parent / "resources" / "ffmpeg" / "ffmpeg.exe"
            exe = alt if alt.exists() else (shutil.which("ffmpeg.exe") or "ffmpeg.exe")
        return str(exe)
    else:
        return shutil.which("ffmpeg") or "ffmpeg"


# ── Song Metadata ───────────────────────────────────────────────────────
async def extract_title_and_artist(url: str):
    """Extract title + artist for a single video."""
    ydl_opts = build_ydl_opts_basic()

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

        title = info.get("track") or info.get("title") or "Unknown Title"
        artist = extract_artist(info)

        return title, artist


# ── Core Playback ───────────────────────────────────────────────────────
async def play_song(vc: discord.VoiceClient, url: str, mention, text_channel, title: str, artist: str):
    """Extract audio URL and start FFmpeg playback."""
    ydl_opts = build_ydl_opts_basic()

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        audio_url = extract_audio_url(info)

    if not audio_url:
        await text_channel.send("Could not find an audio stream for this track.")
        return

    ffmpeg_exe = resolve_ffmpeg_executable()
    ffmpeg_options = {
        "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
        "options": '-vn -af "volume=0.2"',
    }

    vc.play(discord.FFmpegPCMAudio(executable=ffmpeg_exe, source=audio_url, **ffmpeg_options))


# ── Command Handlers ────────────────────────────────────────────────────
async def handle_play_command(interaction: discord.Interaction, url: str, message: discord.WebhookMessage):
    guild_id = interaction.guild_id
    queue = get_guild_queue(guild_id)
    disconnect_requested[guild_id] = False

    url = strip_youtube_playlist(url)

    if not interaction.user.voice:
        await message.edit(content=f"{interaction.user.mention}, you must be in a voice channel.")
        return

    channel = interaction.user.voice.channel

    try:
        title, artist = await extract_title_and_artist(url)
        await message.edit(content="Joining voice channel...")
    except Exception as e:
        await message.edit(content=f"Error fetching song info: {str(e)}")
        return

    await queue.put((channel, url, interaction.user.mention, interaction.channel, title, artist))

    queue_size = queue.qsize()

    if queue_size > 1 or currently_playing.get(guild_id):
        await message.edit(content=f"Added **{title}** by **{artist}** to the queue.")
    else:
        await message.edit(content=f"Now playing **{title}**")

    if not currently_playing.get(guild_id):
        await process_queue(interaction)


async def handle_playlist_command(interaction: discord.Interaction, url: str, songs: int, message: discord.WebhookMessage):
    guild_id = interaction.guild_id
    queue = get_guild_queue(guild_id)
    disconnect_requested[guild_id] = False

    if "list=" not in url:
        await message.edit(content="The URL does not contain a playlist.")
        return

    if not interaction.user.voice:
        await message.edit(content="You must be in a voice channel.")
        return

    channel = interaction.user.voice.channel
    await message.edit(content=f"Fetching playlist... adding first {songs} tracks.")

    ydl_opts = build_ydl_opts_playlist(f"1-{songs}")
    song_details = []

    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            data = ydl.extract_info(url, download=False)
            entries = data.get("entries") or []

            for entry in entries:
                video_id = entry.get("id")
                if not video_id:
                    continue

                song_url = f"https://www.youtube.com/watch?v={video_id}"
                title = entry.get("title", "Unknown Title")
                artist = entry.get("uploader") or "Unknown Artist"

                song_details.append((channel, song_url, interaction.user.mention, interaction.channel, title, artist))

    except Exception as e:
        await message.edit(content=f"Error fetching playlist: {str(e)}")
        return

    if not song_details:
        await message.edit(content="No playlist entries found.")
        return

    if currently_playing.get(guild_id):
        for s in song_details:
            await queue.put(s)
        await message.edit(content="Playlist tracks added to queue.")
    else:
        first = song_details.pop(0)
        title, artist = first[4], first[5]

        await queue.put(first)
        for s in song_details:
            await queue.put(s)

        await message.edit(content=f"Now playing **{title}** by **{artist}**")
        await process_queue(interaction)


async def handle_queue_command(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    queue = get_guild_queue(guild_id)

    if queue.empty() and not currently_playing.get(guild_id):
        await interaction.followup.send("Queue is empty.")
        return

    text = ""

    if current_song.get(guild_id):
        _, _, mention, _, title, artist = current_song[guild_id]
        text += f"**Playing now:** {title} — {artist} (requested by {mention})\n\n"

    qlist = list(queue._queue)
    for i, (_, _, mention, _, title, artist) in enumerate(qlist):
        text += f"{i+1}. {title} — {artist} (requested by {mention})\n"

    await interaction.followup.send(text)


async def handle_disconnect_command(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    queue = get_guild_queue(guild_id)

    vc = interaction.guild.voice_client
    if vc:
        disconnect_requested[guild_id] = True
        await vc.disconnect()

        while not queue.empty():
            queue.get_nowait()

        currently_playing[guild_id] = False
        current_song[guild_id] = None

        await interaction.followup.send("Disconnected and cleared queue.")
    else:
        await interaction.followup.send("Not in a voice channel.")


async def handle_skip_command(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    guild_id = interaction.guild_id
    queue = get_guild_queue(guild_id)

    if vc and vc.is_playing():
        vc.stop()
        await play_next_song(interaction, queue)
    else:
        await interaction.followup.send("Nothing is playing.")


# ── Helpers ─────────────────────────────────────────────────────────────
async def play_next_song(interaction, queue):
    guild_id = interaction.guild_id

    if queue.empty():
        currently_playing[guild_id] = False
        current_song[guild_id] = None
        await interaction.followup.send("Queue finished.")
        return

    next_song = await queue.get()
    current_song[guild_id] = next_song
    channel, url, mention, text_channel, title, artist = next_song

    vc = channel.guild.voice_client or await channel.connect()
    await play_song(vc, url, mention, text_channel, title, artist)

    await interaction.followup.send(f"Now playing: **{title}** by **{artist}**")

    while vc.is_playing():
        await asyncio.sleep(1)

    currently_playing[guild_id] = False
    current_song[guild_id] = None

    await process_queue(interaction)


async def process_queue(interaction):
    guild_id = interaction.guild_id
    queue = get_guild_queue(guild_id)

    while not queue.empty() and not disconnect_requested.get(guild_id):
        currently_playing[guild_id] = True
        song = await queue.get()
        current_song[guild_id] = song

        channel, url, mention, text_channel, title, artist = song
        vc = channel.guild.voice_client or await channel.connect()
        await play_song(vc, url, mention, text_channel, title, artist)

        while vc.is_playing():
            await asyncio.sleep(1)

    currently_playing[guild_id] = False
    current_song[guild_id] = None
