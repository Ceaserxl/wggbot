# main.py

import logging
import discord
from core.config import cfg, cfg_bool
from discord.ext import commands

# -------------------------------------------------------------------
# Logging
# -------------------------------------------------------------------
logging.basicConfig(level=logging.WARNING)

# -------------------------------------------------------------------
# Bot Setup
# -------------------------------------------------------------------
intents = discord.Intents.all()
intents.messages = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix='/', intents=intents)
# -------------------------------------------------------------------
# /ping — global command
# -------------------------------------------------------------------
@bot.tree.command(name="ping", description="Returns the bot's latency.")
async def ping(interaction: discord.Interaction):
    latency = bot.latency * 1000
    await interaction.response.send_message(f"Pong! Latency: {latency:.2f} ms")


# -------------------------------------------------------------------
# Dynamic Module Loader
# -------------------------------------------------------------------
import os
import importlib

def load_modules():
    import os, importlib

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    modules_dir = os.path.join(BASE_DIR, "modules")

    if not os.path.isdir(modules_dir):
        print(f"[WARN] Module folder missing: {modules_dir}")
        return

    for module_folder in os.listdir(modules_dir):
        folder_path = os.path.join(modules_dir, module_folder)

        if not os.path.isdir(folder_path):
            continue

        # must contain __init__.py
        if not os.path.isfile(os.path.join(folder_path, "__init__.py")):
            print(f"[SKIP] No __init__.py in: {folder_path}")
            continue

        module_name = f"modules.{module_folder}"

        try:
            importlib.import_module(module_name)
            print(f"[OK] Loaded module: {module_folder}")
        except Exception as e:
            print(f"[ERR] Failed to load {module_folder}: {e}")

# -------------------------------------------------------------------
# on_ready
# -------------------------------------------------------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    load_modules()
    await bot.tree.sync(guild=discord.Object(1240919439247933521))
    print("Slash commands synced.")


# -------------------------------------------------------------------
# Ollama Listener (remains global)
# -------------------------------------------------------------------
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Thread → base channel
    real_channel = (
        message.channel.parent.id
        if isinstance(message.channel, discord.Thread)
        else message.channel.id
    )

    await bot.process_commands(message)


# -------------------------------------------------------------------
# Entrypoint
# -------------------------------------------------------------------
debug = cfg_bool("wggbot", "debug")
discord_token = cfg("wggbot", "LIVE_DISCORD_TOKEN")
beta_token = cfg("wggbot", "BETA_DISCORD_TOKEN")
if debug:
    discord_token = beta_token
bot.run(discord_token)
