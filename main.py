#main.py

import os, io, base64, requests, asyncio
import sys
import json
import subprocess
import requests
import xmltodict
import time
import hashlib
import logging
import platform
from datetime import datetime
from flask import Flask, render_template, jsonify
import discord
from discord import app_commands
from discord.ext import commands
from discord import ui
from discord.ui import View, Button
from resources import keys
from resources.chatgpt_interaction import (
    handle_dm_message,
    handle_chat_command,
    generate_and_send_image,
    create_help_embed
)
from resources.music_handling import (
    handle_play_command,
    handle_playlist_command,
    handle_disconnect_command,
    handle_skip_command,
    handle_queue_command
)
from resources.conversation import save_conversation_history

# Launch Website
website = False

# Initialize logging
t=logging.getLogger()
logging.basicConfig(level=logging.DEBUG)

# Initialize Discord bot
intents = discord.Intents.all()
intents.messages = True
intents.guilds = True
intents.voice_states = True
bot = commands.Bot(command_prefix='/', intents=intents)

# Conversation history
conversation_history = {}
CONV_FILE = 'resources/jsons/conversation_history.json'

# Plex cache
timestamp_cache = 0
movie_cache = {'data': None, 'timestamp': 0}

# Load conversation history from disk
def load_conversation_history():
    global conversation_history
    if os.path.exists(CONV_FILE):
        conversation_history = json.load(open(CONV_FILE, 'r'))
        print(f"Loaded conversation history for {len(conversation_history)} users.")

# Plex data fetch
def get_plex_data(endpoint):
    headers = {'X-Plex-Token': keys.PLEX_TOKEN}
    resp = requests.get(f"{keys.PLEX_URL}{endpoint}", headers=headers)
    if resp.status_code == 200:
        try:
            return xmltodict.parse(resp.content)
        except Exception as e:
            print(f"XML Parse Error: {e}")
    return None

# Cache movies for 5 minutes
def get_cached_movies():
    now = time.time()
    if now - movie_cache['timestamp'] > 300:
        print("Cache expired, fetching new data.")
        data = get_plex_data('/library/sections/1/all')
        if data:
            movie_cache.update({'data': data, 'timestamp': now})
    else:
        print("Using cached Plex data.")
    return movie_cache['data']

# Extract movie list
def extract_movies(data):
    videos = data.get('MediaContainer', {}).get('Video', [])
    if isinstance(videos, dict): videos = [videos]
    return [f"[{v.get('@ratingKey')}] {v.get('@title')} ({v.get('@year')})" for v in videos]

# Movie paginator view class
class MoviePaginator(View):
    def __init__(self, movie_list, per_page=10):
        super().__init__()
        self.movie_list = movie_list
        self.per_page = per_page
        self.current_page = 0
        self.next_button = Button(label='Next', style=discord.ButtonStyle.primary)
        self.prev_button = Button(label='Previous', style=discord.ButtonStyle.primary)
        self.next_button.callback = self.next_page
        self.prev_button.callback = self.prev_page
        self.add_item(self.prev_button)
        self.add_item(self.next_button)

    def get_embed(self):
        start = self.current_page * self.per_page
        end = start + self.per_page
        chunk = self.movie_list[start:end]
        return discord.Embed(title="Movie List", description="\n".join(chunk), color=discord.Color.blue())

    async def next_page(self, interaction):
        if (self.current_page+1)*self.per_page < len(self.movie_list):
            self.current_page += 1
            await interaction.response.edit_message(embed=self.get_embed(), view=self)

    async def previous_page(self, interaction):
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.get_embed(), view=self)

@bot.tree.command(name="ping", description="Returns the bot's latency.")
async def ping(interaction: discord.Interaction):
    print("Executing /ping")
    latency = bot.latency * 1000  # Convert to milliseconds
    await interaction.response.send_message(f"Pong! Latency: {latency:.2f} ms", ephemeral=True)


@bot.tree.command(name="help", description="Shows the help message.")
async def help(interaction: discord.Interaction):
    print("Executing /help")
    embed = create_help_embed(user_mention=interaction.user.mention)
    await interaction.response.send_message(embed=embed, ephemeral=False)  # Set ephemeral to False


@bot.tree.command(name="chat", description="Chat with the bot using a prompt.")
async def chat(interaction: discord.Interaction, prompt: str):
    print("Executing /chat")
    if isinstance(interaction.channel, discord.DMChannel):
        await interaction.response.send_message("You don't need to use /chat here. Just type normally", ephemeral=True)
    else:
        await interaction.response.defer()
        await handle_chat_command(interaction, prompt, conversation_history, bot)


@bot.tree.command(name="image", description="Generate an image using Dall-E.")
async def image(interaction: discord.Interaction, prompt: str):
    print("Executing /image")
    await interaction.response.defer(thinking=True)  # Display "bot is thinking"

    # Generate and send the image
    await generate_and_send_image(interaction, prompt, conversation_history)

SD_API_URL      = keys.SD_API_URL
SD_WIDTH        = 512
SD_HEIGHT       = 512
hr_scale        = 1.5
neg_prompt      = "low quality, blurry, deformed, bad anatomy, bad quality, worst quality, worst detail, sketch, signature, watermark, username, patreon"
generation_lock = asyncio.Lock()
pending_requests = []
pending_messages: list[discord.Message] = []

@bot.tree.command(name="imagine", description="Generate an image using Stable Diffusion")
@app_commands.choices(
    size=[
        # Normal Sizing
        app_commands.Choice(name="Square",              value="512x512"),
        app_commands.Choice(name="Portrait",            value="512x768"),
        app_commands.Choice(name="Wide",                value="768x512"),
    ]
)
@app_commands.choices(
    model=[
        app_commands.Choice(name="dynavisionXLAllInOneStylized_releaseV0610Bakedvae",   value="dynavisionXLAllInOneStylized_releaseV0610Bakedvae"),
        app_commands.Choice(name="waiNSFWIllustrious_v120",                             value="waiNSFWIllustrious_v120"),
        app_commands.Choice(name="illustrij_v13",                                       value="illustrij_v13"),
        app_commands.Choice(name="cyberrealisticPony_v11",                              value="cyberrealisticPony_v11"),
        app_commands.Choice(name="illustriousRealism_v10",                              value="illustriousRealismBy_v10"),
        app_commands.Choice(name="realDream_SDXL",                                      value="realDream_sdxlPony15"),
        app_commands.Choice(name="realisticVisionV60B1_v51HyperVAE",                    value="realisticVisionV60B1_v51HyperVAE"),
        app_commands.Choice(name="revAnimated_v2RebirthVAE",                            value="revAnimated_v2RebirthVAE"),
        app_commands.Choice(name="dreamshaper_8",                                       value="dreamshaper_8"),
    ]
)

async def imagine(
    interaction: discord.Interaction,
    prompt: str,
    size: str = "512x512",
    model: str = "dynavisionXLAllInOneStylized_releaseV0610Bakedvae",
    refiner: bool = False,
    seed: int = -1
):
    session = requests.Session()
    await interaction.response.defer()
    #Square 512x512
    if size == "512x512":
        SD_WIDTH        = 512
        SD_HEIGHT       = 512
    #Wide 768x512
    elif size == "768x512":
        SD_WIDTH        = 768
        SD_HEIGHT       = 512
    #Portrait 512x768
    elif size == "512x768":
        SD_WIDTH        = 512
        SD_HEIGHT       = 768

    # 2️⃣ Queue position
    await interaction.followup.send(f"⏳ You are #{len(pending_messages)+1} in queue. Please wait…")
    msg = await interaction.original_response()
    pending_messages.append(msg)

    async with generation_lock:
        # update other queue positions
        pending_messages.pop(0)
        for idx, m in enumerate(pending_messages):
            await m.edit(content=f"⏳ You are #{idx+1} in queue. Please wait…")

        # 🖼️ Initial embed
        embed = discord.Embed(
            title="🎨 Generating Image 🎨",
            color=discord.Color.green(),
            description="\n".join([
                f"**Prompt:**\n```{prompt}```",
                f"**Model:**\n```{model}```",
                f"**Resolution:**\n```{SD_WIDTH}×{SD_HEIGHT}```"
            ])
        )
        embed.set_footer(text="Progress: 0.0% • ETA: --s")
        progress_msg = await msg.edit(content=None, embed=embed)

        # 3️⃣ Start generation task
        start_time = time.time()
        loop = asyncio.get_running_loop()
        
        # before starting the thread:
        base_payload = {
            "prompt": prompt,
            "negative_prompt": neg_prompt,
            "width": SD_WIDTH,
            "height": SD_HEIGHT,
            "steps": 20,
            "sampler_name": "DPM++ 2M",
            "scheduler": "Karras",
            "hr_scale": hr_scale,
            "hr_upscaler": "Latent",
            "hr_second_pass_steps": 10,
            "denoising_strength": 0.7,
            "save_images": True,
            "seed": seed,
            "override_settings": {
                "sd_model_checkpoint": model
            }
        }
 
        # only add these if refiner == True
        if refiner:
            base_payload.update({
                "enable_refiner": True,
                "refiner_checkpoint": "realDream_sdxlRealismRefinerV2.safetensors",
                "refiner_switch_at": 0.8
            })

        # then:
        gen_task = loop.run_in_executor(
            None,
            lambda: session.post(
                f"{SD_API_URL}/sdapi/v1/txt2img",
                json=base_payload,
                timeout=999
            )
        )

        # 4️⃣ Poll progress using the same session
        progress_url = f"{SD_API_URL}/sdapi/v1/progress?skip_current_image=false"
        while not gen_task.done():
            pr = session.get(progress_url, timeout=10).json()
            pct = pr.get("progress", 0.0) * 100
            eta = int(pr.get("eta_relative", 0))
            embed.set_footer(text=f"Progress: {pct:.1f}% • ETA: {eta}s")

            if pr.get("current_image"):
                preview = base64.b64decode(pr["current_image"].split(",",1)[-1])
                file = discord.File(io.BytesIO(preview), filename="preview.png")
                embed.set_image(url="attachment://preview.png")
                await progress_msg.edit(embed=embed, attachments=[file])
            else:
                await progress_msg.edit(embed=embed)

            await asyncio.sleep(1)


        # 5️⃣ Final result + seed + duration
        resp = gen_task.result(); resp.raise_for_status()
        result = resp.json()
        info = json.loads(result.get("info", "{}"))
        used_seed = info.get("seed", "unknown")
        duration = time.time() - start_time

        final_bytes = base64.b64decode(result["images"][0])
        save_dir = "images"
        os.makedirs(save_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}.png"
        path = os.path.join(save_dir, filename)
        with open(path, "wb") as f:
            f.write(final_bytes)

        final_file = discord.File(path, filename=filename)
        embed.set_footer(text=f"Seed: {used_seed} • Time: {duration:.1f}s")
        embed.set_image(url=f"attachment://{filename}")

        class UpscaleButton(discord.ui.View):
            def __init__(self, seed, model, prompt, neg_prompt, width, height, filename):
                super().__init__(timeout=None)
                self.seed = seed
                self.model = model
                self.prompt = prompt
                self.neg_prompt = neg_prompt
                self.width = width
                self.height = height
                self.filename = filename

            @discord.ui.button(label="Upscale 1.5x", style=discord.ButtonStyle.primary)
            async def upscale(self, interaction: discord.Interaction, button: discord.ui.Button):
                await interaction.response.defer()

                try:
                    # 1️⃣ Load original image and prepare payload
                    image_path = f"images/{self.filename}"
                    with open(image_path, "rb") as img_file:
                        image_bytes = img_file.read()
                        image_base64 = base64.b64encode(image_bytes).decode()

                    upscale_payload = {
                        "init_images": [f"data:image/png;base64,{image_base64}"],
                        "prompt": self.prompt,
                        "negative_prompt": self.neg_prompt,
                        "seed": self.seed,
                        "steps": 20,
                        "sampler_name": "DPM++ 2M",
                        "scheduler": "Karras",
                        "denoising_strength": 0.7,
                        "width": int(self.width * 1.5),
                        "height": int(self.height * 1.5),
                        "override_settings": {
                            "sd_model_checkpoint": self.model
                        }
                    }

                    # 2️⃣ Upscale embed with polished formatting (no fields)
                    embed = discord.Embed(
                        title="🆙 Upscaling Image 🆙",
                        color=discord.Color.blurple(),
                        description="\n".join([
                            f"**Prompt:**\n```{self.prompt}```",
                            f"**Model:**\n```{self.model}```",
                            f"**Target Resolution:**\n```{int(self.width * 1.5)}×{int(self.height * 1.5)}```"
                        ])
                    )
                    embed.set_footer(text="Upscaling... 0.0% • ETA: --s")
                    msg = await interaction.followup.send(embed=embed, wait=True)

                    # 3️⃣ Start upscale task
                    loop = asyncio.get_running_loop()
                    start_time = time.time()
                    upscale_task = loop.run_in_executor(None, lambda: requests.post(
                        f"{SD_API_URL}/sdapi/v1/img2img",
                        json=upscale_payload,
                        timeout=999
                    ))

                    # 4️⃣ Poll progress + update preview
                    progress_url = f"{SD_API_URL}/sdapi/v1/progress?skip_current_image=false"
                    while not upscale_task.done():
                        pr = session.get(progress_url, timeout=10).json()
                        pct = pr.get("progress", 0.0) * 100
                        eta = int(pr.get("eta_relative", 0))
                        embed.set_footer(text=f"Upscaling... {pct:.1f}% • ETA: {eta}s")

                        if pr.get("current_image"):
                            preview = base64.b64decode(pr["current_image"].split(",", 1)[-1])
                            preview_file = discord.File(io.BytesIO(preview), filename="preview.png")
                            embed.set_image(url="attachment://preview.png")
                            await msg.edit(embed=embed, attachments=[preview_file])
                        else:
                            await msg.edit(embed=embed)

                        await asyncio.sleep(2)

                    # 5️⃣ Done — get final image
                    resp = upscale_task.result()
                    resp.raise_for_status()
                    result = resp.json()
                    final_image = base64.b64decode(result["images"][0])
                    duration = time.time() - start_time

                    file = discord.File(io.BytesIO(final_image), filename="upscaled.png")
                    embed.set_image(url="attachment://upscaled.png")
                    embed.set_footer(text=f"Seed: {self.seed} • Time: {duration:.1f}s")
                    await msg.edit(embed=embed, attachments=[file])

                except Exception as e:
                    await interaction.followup.send(f"❌ Upscale failed: `{e}`")

        view = UpscaleButton(used_seed, model, prompt, neg_prompt, SD_WIDTH, SD_HEIGHT, filename)
        await progress_msg.edit(embed=embed, attachments=[final_file], view=view)
        session.close()

@bot.tree.command(name="play", description="Play a song from a YouTube link.")
async def play(interaction: discord.Interaction, link: str):
    print("Executing /play")
    if isinstance(interaction.channel, discord.DMChannel):
        await interaction.response.send_message("Those commands cannot be used here", ephemeral=True)
    else:
        await interaction.response.defer()
        message = await interaction.followup.send("Fetching song info from URL...")

        # Fetch song info and join the voice channel
        try:
            await handle_play_command(interaction, link, message)
        except Exception as e:
            await message.edit(content=f"Error: {str(e)}")


@bot.tree.command(name="playlist", description="Play a playlist from a YouTube link.")
async def playlist(interaction: discord.Interaction, link: str, songs: int = 5):
    print("Executing /playlist")
    if isinstance(interaction.channel, discord.DMChannel):
        await interaction.response.send_message("Those commands cannot be used here", ephemeral=True)
    else:
        await interaction.response.defer()
        message = await interaction.followup.send("Fetching playlist info from URL...")

        try:
            await handle_playlist_command(interaction, link, songs, message)
        except Exception as e:
            await message.edit(content=f"Error: {str(e)}")


@bot.tree.command(name="skip", description="Skip the current song.")
async def skip(interaction: discord.Interaction):
    print("Executing /skip")
    if isinstance(interaction.channel, discord.DMChannel):
        await interaction.response.send_message("Those commands cannot be used here", ephemeral=True)
    else:
        await interaction.response.defer()
        await handle_skip_command(interaction)


@bot.tree.command(name="queue", description="Show the current song queue.")
async def queue(interaction: discord.Interaction):
    print("Executing /queue")
    if isinstance(interaction.channel, discord.DMChannel):
        await interaction.response.send_message("Those commands cannot be used here", ephemeral=True)
    else:
        await interaction.response.defer()
        await handle_queue_command(interaction)


@bot.tree.command(name="disconnect", description="Disconnect the bot from the voice channel.")
async def disconnect(interaction: discord.Interaction):
    print("Executing /disconnect")
    if isinstance(interaction.channel, discord.DMChannel):
        await interaction.response.send_message("Those commands cannot be used here", ephemeral=True)
    else:
        await interaction.response.defer()
        await handle_disconnect_command(interaction)


@bot.tree.command(name="movies", description="Fetch the list of movies.")
async def movies(interaction: discord.Interaction):
    print("Executing /movies")
    data = get_cached_movies()
    if data:
        movie_list = extract_movies(data)
        paginator = MoviePaginator(movie_list)
        await interaction.response.send_message(embed=paginator.get_embed(), view=paginator)
    else:
        await interaction.response.send_message('Failed to fetch movie data.', ephemeral=True)


@bot.tree.command(name="search", description="Search for a movie.")
async def search(interaction: discord.Interaction, query: str):
    print("Executing /search")
    data = get_plex_data(f'/search?query={query}')
    if data:
        movie_list = extract_movies(data)
        paginator = MoviePaginator(movie_list)
        await interaction.response.send_message(embed=paginator.get_embed(), view=paginator)
    else:
        await interaction.response.send_message('Failed to search for movies.', ephemeral=True)


@bot.tree.command(name="watch", description="Get a link to watch a movie.")
async def watch(interaction: discord.Interaction, movie_id: int):
    print("Executing /watch")
    data = get_plex_data(f'/library/metadata/{movie_id}')
    if data:
        movie_title = data['MediaContainer']['Video'].get('@title', 'Unknown Title')
        direct_movie_url = f"{keys.PLEX_URL}{data['MediaContainer']['Video']['Media']['Part']['@key']}?X-Plex-Token={keys.PLEX_TOKEN}"
        room_id = hashlib.md5(direct_movie_url.encode()).hexdigest()
        print(keys.APP_URL)
        # Create the room
        room_creation_response = requests.post(f'http://{keys.APP_URL}:5000/create',
                                               data={'video_url': direct_movie_url})
        if room_creation_response.status_code == 200:
            watch_together_url = f"http://{keys.APP_URL}:5000/room/{room_id}"
            embed = discord.Embed(
                title=f"Watch {movie_title}",
                description="Click the buttons below to watch the movie together or directly",
                color=discord.Color.blue()
            )
            embed.add_field(name="Direct Movie Link", value=f"[Watch Directly]({direct_movie_url})", inline=False)
            embed.add_field(name="Watch Together Link", value=f"[Watch Together]({watch_together_url})", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=False)
        else:
            await interaction.response.send_message('Failed to create a watch room.', ephemeral=True)
    else:
        await interaction.response.send_message('Failed to fetch movie data.', ephemeral=True)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    #await bot.change_presence(activity=discord.Game(name="/help"))
    await bot.tree.sync()

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    user_id = str(message.author.id)
    if user_id not in conversation_history:
        #print("New user detected.")
        conversation_history[user_id] = [keys.SYSTEM_MESSAGE]
        conversation_history[user_id].append({
            "role": "user",
            "content": "NEW USER FILLER",
            "timestamp": datetime.utcnow().isoformat()
        })
        #save_conversation_history(conversation_history)
    bot.loop.create_task(process_message(message, user_id))

async def process_message(message, user_id):
    if isinstance(message.channel, discord.DMChannel):
        await handle_dm_message(message, conversation_history)

if __name__ == '__main__':
    # Launch website.py alongside the Discord bot
    print("Starting website.py and Discord bot...")
    if website == True:
        subprocess.Popen([sys.executable, os.path.join(os.path.dirname(__file__), 'website.py')])
    # Load history and run bot
    #load_conversation_history()
    bot.run(keys.DISCORD_TOKEN)
