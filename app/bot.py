# bot.py

import os
import logging
import discord
from discord.ext import commands

from core.config import cfg, cfg_bool
from core.module_loader import load_all_modules

# ---------------------------------------------------------
# Logging
# ---------------------------------------------------------
logging.basicConfig(level=logging.WARNING)

# ---------------------------------------------------------
# Bot Setup
# ---------------------------------------------------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="/", intents=intents)


# ---------------------------------------------------------
# Discord Events
# ---------------------------------------------------------
@bot.event
async def on_ready():
    print(f"\nLogged in as {bot.user}")

    try:
        synced = await bot.tree.sync()
        print(f"[SYNC] Synced {len(synced)} commands")
    except Exception as e:
        print(f"[ERR] Slash command sync failed: {e}")

# ---------------------------------------------------------
# Entry Point
# ---------------------------------------------------------
if __name__ == "__main__":

    print("\n===========================================")
    print("            Starting WGGBot...")
    print("===========================================\n")

    # Load modules BEFORE connecting to Discord
    load_all_modules(bot)

    debug = cfg_bool("wggbot", "debug")
    token = cfg("wggbot", "BETA_DISCORD_TOKEN" if debug else "LIVE_DISCORD_TOKEN")
    bot.run(token)
