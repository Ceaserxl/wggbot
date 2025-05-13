# main.py

# ── Imports ─────────────────────────────────────────────────────────────
import asyncio
import logging
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from resources import keys
from resources.chatgpt_interaction import (
    handle_dm_message,
    handle_chat_command,
    generate_and_send_image,
)
from resources.music_handling import (
    handle_play_command,
    handle_playlist_command,
    handle_disconnect_command,
    handle_skip_command,
    handle_queue_command
)
from resources.stable_diffusion import UpscaleButton, imagine_command
from resources.ollama import query_ollama
from resources.ollama import handle_ollama_response

# ── Constants ────────────────────────────────────────────────────────────
OLLAMA_CHANNEL_ID = keys.OLLAMA_CHANNEL_ID

# ── Logging Setup ────────────────────────────────────────────────────────
t = logging.getLogger()
logging.basicConfig(level=logging.DEBUG)

# ── Discord Bot Setup ────────────────────────────────────────────────────
intents = discord.Intents.all()
intents.messages = True
intents.guilds = True
intents.voice_states = True
bot = commands.Bot(command_prefix='/', intents=intents)

# ── Bot Commands ─────────────────────────────────────────────────────────
@bot.tree.command(name="ping", description="Returns the bot's latency.")
async def ping(interaction: discord.Interaction):
    print("Executing /ping")
    latency = bot.latency * 1000  # Convert to milliseconds
    await interaction.response.send_message(f"Pong! Latency: {latency:.2f} ms")

@bot.tree.command(name="chat", description="Chat with the bot using a prompt.")
async def chat(interaction: discord.Interaction, prompt: str):
    print("Executing /chat")
    if isinstance(interaction.channel, discord.DMChannel):
        await interaction.response.send_message("You don't need to use /chat here. Just type normally", ephemeral=True)
    else:
        await interaction.response.defer()
        await handle_chat_command(interaction, prompt, bot)

@bot.tree.command(name="play", description="Play a song from a YouTube link.")
async def play(interaction: discord.Interaction, link: str):
    print("Executing /play")
    if isinstance(interaction.channel, discord.DMChannel):
        await interaction.response.send_message("Those commands cannot be used here", ephemeral=True)
    else:
        await interaction.response.defer()
        message = await interaction.followup.send("Fetching song info from URL...")
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

@bot.tree.command(name="image", description="Generate an image using Dall-E.")
async def image(interaction: discord.Interaction, prompt: str):
    print("Executing /image")
    await interaction.response.defer(thinking=True)
    await generate_and_send_image(interaction, prompt)

@bot.tree.command(name="imagine", description="Generate an image using Stable Diffusion")
@app_commands.choices(
    size=[
        app_commands.Choice(name="Square",   value="512x512"),
        app_commands.Choice(name="Portrait", value="512x768"),
        app_commands.Choice(name="Landscape",value="768x512"),
    ]
)
@app_commands.choices(
    model=[
        app_commands.Choice(name="dynavisionXLAllInOneStylized_releaseV0610Bakedvae",   value="dynavisionXLAllInOneStylized_releaseV0610Bakedvae"),
        app_commands.Choice(name="waiNSFWIllustrious_v120",                             value="waiNSFWIllustrious_v120"),
        app_commands.Choice(name="illustrij_v13",                                       value="illustrij_v13"),
        app_commands.Choice(name="cyberrealisticPony_v11",                              value="cyberrealisticPony_v11"),
        app_commands.Choice(name="illustriousRealismBy_v10",                            value="illustriousRealismBy_v10"),
        app_commands.Choice(name="realDream_sdxlPony15",                                value="realDream_sdxlPony15"),
        app_commands.Choice(name="realisticVisionV60B1_v51HyperVAE",                    value="realisticVisionV60B1_v51HyperVAE"),
        app_commands.Choice(name="revAnimated_v2RebirthVAE",                            value="revAnimated_v2RebirthVAE"),
        app_commands.Choice(name="dreamshaper_8",                                       value="dreamshaper_8"),
        app_commands.Choice(name="disneyPixarCartoon_v10",                              value="disneyPixarCartoon_v10")
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
    await imagine_command(interaction, prompt, size, model, refiner, seed)

# ── Event Listeners ─────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await bot.tree.sync()
 
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # DMs
    if isinstance(message.channel, discord.DMChannel):
        await handle_dm_message(message)
        return

    # figure out the “real” channel ID: thread→parent, else itself
    channel_id = (
        message.channel.parent.id
        if isinstance(message.channel, discord.Thread)
        else message.channel.id
    )

    if channel_id == OLLAMA_CHANNEL_ID:
        bot.loop.create_task(handle_ollama_response(message))
        return

    # if you have other on_message logic, call this to let commands still work
    await bot.process_commands(message)

# ── Main Entrypoint ─────────────────────────────────────────────────────
if __name__ == '__main__':
    bot.run(keys.DISCORD_TOKEN)
