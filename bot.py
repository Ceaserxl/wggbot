# app/bot.py
import asyncio
import json
import os
import discord
from discord.ext import commands
from core.config import cfg, cfg_bool
from core.module_loader import load_all_modules
from core.logging import log
# ---------------------------------------------------------
# Bot Setup
# ---------------------------------------------------------
class WGGBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="/", intents=discord.Intents.all())
        self.health_server = None

    async def setup_hook(self):
        health_host = os.getenv("HEALTH_HOST", "0.0.0.0")
        health_port = int(os.getenv("HEALTH_PORT", "8080"))
        self.health_server = await asyncio.start_server(
            self.handle_health_check,
            health_host,
            health_port,
        )
        log(f"[HEALTH] Listening on {health_host}:{health_port}")

    async def handle_health_check(self, reader, writer):
        try:
            await asyncio.wait_for(reader.read(4096), timeout=2)
            ready = self.is_ready() and not self.is_closed()
            status = "200 OK" if ready else "503 Service Unavailable"
            body = json.dumps({"status": "ok" if ready else "starting"}) + "\n"
            response = (
                f"HTTP/1.1 {status}\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(body.encode('utf-8'))}\r\n"
                "Connection: close\r\n"
                "\r\n"
                f"{body}"
            )
            writer.write(response.encode("utf-8"))
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def close(self):
        if self.health_server is not None:
            self.health_server.close()
            await self.health_server.wait_closed()
        await super().close()


bot = WGGBot()

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
