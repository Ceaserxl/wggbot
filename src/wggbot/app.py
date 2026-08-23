from __future__ import annotations

import logging
from typing import Any

import discord
from discord.ext import commands

from .health import HealthServer
from .logging import configure_logging
from .music.cog import MusicCog
from .settings import Settings, load_settings

LOGGER = logging.getLogger(__name__)


class WGGBot(commands.Bot):
    def __init__(self, settings: Settings):
        # All intents are an intentional product requirement for this bot.
        super().__init__(command_prefix="/", intents=discord.Intents.all())
        self.settings = settings
        self.music = MusicCog(self)
        self.health = HealthServer(
            settings.health_host,
            settings.health_port,
            self.health_snapshot,
        )

    async def setup_hook(self) -> None:
        await self.add_cog(self.music)
        await self.health.start()
        LOGGER.info(
            "Health endpoint listening on %s:%s",
            self.settings.health_host,
            self.settings.health_port,
        )
        if self.settings.sync_commands:
            synced = await self.tree.sync()
            LOGGER.info("Synced %d application commands", len(synced))

    async def on_ready(self) -> None:
        LOGGER.info("Connected to Discord as %s", self.user)

    async def on_disconnect(self) -> None:
        LOGGER.warning("Discord connection lost")

    def health_snapshot(self) -> tuple[int, dict[str, Any]]:
        ready = self.is_ready() and not self.is_closed()
        return (
            200 if ready else 503,
            {
                "status": "ok" if ready else "starting",
                "discord": "connected" if ready else "disconnected",
                "music": "ready",
            },
        )

    async def close(self) -> None:
        await self.health.close()
        await self.music.close()
        await super().close()


async def run() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)
    bot = WGGBot(settings)
    async with bot:
        await bot.start(settings.discord_token, reconnect=True)
