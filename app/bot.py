# app/bot.py
import os
import discord
from discord.ext import commands
from app.core.config import cfg, cfg_bool
from app.core.module_loader import load_all_modules
from app.core.logging import log
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
    log(f"Logged in as {bot.user}")

    try:
        synced = await bot.tree.sync()
        log(f"[SYNC] Synced {len(synced)} commands")
    except Exception as e:
        log(f"[ERR] Slash command sync failed: {e}")

# ---------------------------------------------------------
# Entry Point
# ---------------------------------------------------------
if __name__ == "__main__":
    log("===========================================")
    log("            Starting WGGBot...")
    log("===========================================")
    # Load modules BEFORE connecting to Discord
    load_all_modules(bot)
    debug = cfg_bool("wggbot", "debug")
    token = cfg("wggbot", "BETA_DISCORD_TOKEN" if debug else "LIVE_DISCORD_TOKEN")
    bot.run(token)
