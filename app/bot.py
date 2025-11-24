# main.py

import logging
import discord
import core.config
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
    base_path = "modules"

    for module_folder in os.listdir(base_path):
        folder_path = os.path.join(base_path, module_folder)

        # Skip non-folders
        if not os.path.isdir(folder_path):
            continue

        # Look for commands.py inside the folder
        commands_file = os.path.join(folder_path, "commands.py")
        if not os.path.isfile(commands_file):
            continue

        import_path = f"{base_path}.{module_folder}.commands"

        try:
            module = importlib.import_module(import_path)
            if hasattr(module, "setup"):
                module.setup(bot)
                print(f"Loaded module: {import_path}")
        except Exception as e:
            print(f"Failed to load module {import_path}: {e}")


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
bot.run(keys.DISCORD_TOKEN)
