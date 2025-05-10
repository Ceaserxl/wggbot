# resources/music_handling.py

import yt_dlp as youtube_dl
import discord
import asyncio
import re

queues = {}  # Dictionary to store queues for each guild
currently_playing = {}  # Dictionary to track currently playing song for each guild
disconnect_requested = {}  # Dictionary to track disconnect requests for each guild
current_song = {}  # Dictionary to track the current song for each guild

def get_guild_queue(guild_id):
    if guild_id not in queues:
        queues[guild_id] = asyncio.Queue()
    return queues[guild_id]

def strip_youtube_playlist(url):
    return re.sub(r'(\?|&)list=[^&]*', '', url)

async def handle_play_command(interaction: discord.Interaction, url: str, message: discord.WebhookMessage):
    guild_id = interaction.guild_id
    queue = get_guild_queue(guild_id)
    disconnect_requested[guild_id] = False

    url = strip_youtube_playlist(url)

    if not interaction.user.voice:
        await message.edit(
            content=f"{interaction.user.mention}, You need to be in a voice channel to use this command.")
        return

    channel = interaction.user.voice.channel

    # Fetch song info
    try:
        title, artist = await extract_title_and_artist(url)
        await message.edit(content="Joining voice channel...")
    except Exception as e:
        await message.edit(content=f"Error fetching song info: {str(e)}")
        return

    # Add the song to the queue
    await queue.put((channel, url, interaction.user.mention, interaction.channel, title, artist))

    # Notify the user that the song has been added to the queue with the song title and artist
    queue_size = queue.qsize()
    if queue_size > 1 or currently_playing.get(guild_id):
        await message.edit(
            content=f"{interaction.user.mention}, your song **{title}** by **{artist}** has been added to the queue. There are now {queue_size} song(s) in the queue.")
    else:
        await message.edit(content=f"Now playing **{title}** requested by {interaction.user.mention}")

    if not currently_playing.get(guild_id):
        await process_queue(interaction)

async def handle_playlist_command(interaction: discord.Interaction, url: str, songs: int, message: discord.WebhookMessage):
    guild_id = interaction.guild_id
    queue = get_guild_queue(guild_id)
    disconnect_requested[guild_id] = False

    if 'list=' not in url:
        await message.edit(content="The URL does not contain a playlist.")
        return

    if not interaction.user.voice:
        await message.edit(
            content=f"{interaction.user.mention}, You need to be in a voice channel to use this command.")
        return

    channel = interaction.user.voice.channel
    await message.edit(content=f"{interaction.user.mention}, fetching playlist...adding first {songs} songs I see.")

    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'force_generic_extractor': True,
        'playlist_items': f'1-{songs}',  # Adjust to only get the first {songs} songs
    }

    song_details = []
    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            playlist_info = ydl.extract_info(url, download=False)
            if 'entries' in playlist_info:
                for entry in playlist_info['entries']:
                    song_url = f"https://www.youtube.com/watch?v={entry['id']}"
                    title = entry.get('title', 'Unknown Title')
                    artist = entry.get('uploader', 'Unknown Artist')
                    song_details.append(
                        (channel, song_url, interaction.user.mention, interaction.channel, title, artist))
    except Exception as e:
        await message.edit(content=f"Error fetching playlist info: {str(e)}")
        return

    if song_details:
        if currently_playing.get(guild_id):
            for song in song_details:
                await queue.put(song)
            combined_message = f"{interaction.user.mention}, the following songs have been added to the queue:\n- " + "\n- ".join(
                [f"**{title}** by **{artist}**" for _, _, _, _, title, artist in song_details])
            await message.edit(content=combined_message)
        else:
            first_song = song_details.pop(0)
            channel, url, mention, text_channel, title, artist = first_song
            combined_message = f"Now playing **{title}** by **{artist}** requested by {mention}\n\n"
            if song_details:
                combined_message += "The following songs have been added to the queue:\n- " + "\n- ".join(
                    [f"**{title}** by **{artist}**" for _, _, _, _, title, artist in song_details])
            await queue.put(first_song)
            for song in song_details:
                await queue.put(song)
            await message.edit(content=combined_message)
            await process_queue(interaction)
    else:
        await message.edit(content="No entries found in the playlist.")

async def handle_queue_command(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    queue = get_guild_queue(guild_id)
    if queue.empty() and not currently_playing.get(guild_id):
        await interaction.followup.send("The queue is currently empty.")
    else:
        songs = list(queue._queue)  # Copy the current queue
        queue_list = ""
        if current_song.get(guild_id):
            queue_list += f"Currently playing:\n{current_song[guild_id][4]} by {current_song[guild_id][5]} (requested by {current_song[guild_id][2]})\n\n"
        for i, (channel, url, mention, text_channel, title, artist) in enumerate(songs):
            queue_list += f"{i + 1}. {title} by {artist} (requested by {mention})\n"
        await interaction.followup.send(f"Current queue:\n{queue_list}")

async def process_queue(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    queue = get_guild_queue(guild_id)
    while not queue.empty() and not disconnect_requested.get(guild_id):
        currently_playing[guild_id] = True
        current_song[guild_id] = await queue.get()

        channel, url, mention, text_channel, title, artist = current_song[guild_id]

        if not channel.guild.voice_client:
            vc = await channel.connect()
        else:
            vc = channel.guild.voice_client

        await play_song(vc, url, mention, text_channel, title, artist)

        while vc.is_playing():
            await asyncio.sleep(1)

    currently_playing[guild_id] = False
    current_song[guild_id] = None

async def handle_disconnect_command(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    queue = get_guild_queue(guild_id)

    if interaction.guild.voice_client:
        disconnect_requested[guild_id] = True
        await interaction.followup.send(f"{interaction.user.mention} disconnected me from the voice channel.")
        await interaction.guild.voice_client.disconnect()

        # Clear the queue and reset currently playing song
        while not queue.empty():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        currently_playing[guild_id] = False
        current_song[guild_id] = None
    else:
        await interaction.followup.send("I am not in a voice channel.")

async def handle_skip_command(interaction: discord.Interaction):
    guild_id = interaction.guild_id
    queue = get_guild_queue(guild_id)

    if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
        interaction.guild.voice_client.stop()

        # Play the next song in the queue
        await play_next_song(interaction, queue)
    else:
        await interaction.followup.send(f"{interaction.user.mention}, there is no song currently playing.")

async def play_next_song(interaction: discord.Interaction, queue: asyncio.Queue):
    guild_id = interaction.guild_id
    if not queue.empty():
        next_song = await queue.get()
        current_song[guild_id] = next_song
        channel, url, mention, text_channel, title, artist = next_song
        await interaction.followup.send(
            f"Skipped the current song. Now playing: **{title}** by **{artist}** requested by {mention}")

        if not channel.guild.voice_client:
            vc = await channel.connect()
        else:
            vc = channel.guild.voice_client

        await play_song(vc, url, mention, text_channel, title, artist)

        while vc.is_playing():
            await asyncio.sleep(1)

        currently_playing[guild_id] = False
        current_song[guild_id] = None
        await process_queue(interaction)
    else:
        await interaction.followup.send(
            f"{interaction.user.mention}, the current song has been skipped. No more songs in the queue.")

async def join_and_play(channel, url, mention, text_channel):
    title, artist = await extract_title_and_artist(url)
    await text_channel.send(f"{mention}, now playing: **{title}** by **{artist}**")
    vc = await channel.connect()
    await play_song(vc, url, mention, text_channel, title, artist)

async def play_song(vc, url, mention, text_channel, title, artist):
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'extract_flat': 'in_playlist',
        'force_generic_extractor': True,
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=False)
        audio_url = info_dict['url']

    if audio_url:
        ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn -af "volume=0.1"'
        }

        vc.play(discord.FFmpegPCMAudio(executable="ffmpeg", source=audio_url, **ffmpeg_options))
    else:
        await text_channel.send("Could not find a matching audio track for the provided link.")

async def extract_title_and_artist(url):
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'extract_flat': 'in_playlist',
        'force_generic_extractor': True,
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=False)
        title = info_dict.get('title', 'Unknown Title')
        artist = info_dict.get('artist', 'Unknown Artist')
        return title, artist
