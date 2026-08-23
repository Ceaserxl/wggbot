from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import discord
from discord.ext import commands

from core.logging import configure_logging
from core.module_manager import ModuleManager, ModulesCog
from core.settings import Settings, load_settings


class WGGBot(commands.Bot):
    def __init__(self, settings: Settings):
        # All intents are an intentional product requirement for this bot.
        super().__init__(command_prefix="/", intents=discord.Intents.all())
        self.settings = settings
        self.module_manager = ModuleManager(self, settings.module_state_path)
        self.health_server: asyncio.AbstractServer | None = None
        self.ready_event = asyncio.Event()

    async def setup_hook(self) -> None:
        await self.add_cog(ModulesCog(self, self.module_manager))
        await self.module_manager.load_enabled()
        self.health_server = await asyncio.start_server(
            self._handle_health_check,
            self.settings.health_host,
            self.settings.health_port,
        )
        logging.getLogger(__name__).info(
            "Health endpoint listening on %s:%s",
            self.settings.health_host,
            self.settings.health_port,
        )
        if self.settings.sync_commands:
            synced = await self.tree.sync()
            logging.getLogger(__name__).info("Synced %d application commands", len(synced))

    async def on_ready(self) -> None:
        self.ready_event.set()
        logging.getLogger(__name__).info("Connected to Discord as %s", self.user)

    async def on_disconnect(self) -> None:
        self.ready_event.clear()
        logging.getLogger(__name__).warning("Discord connection lost")

    def health_snapshot(self) -> tuple[int, dict[str, Any]]:
        ready = self.ready_event.is_set() and not self.is_closed()
        return (
            200 if ready else 503,
            {
                "status": "ok" if ready else "starting",
                "discord": "connected" if ready else "disconnected",
                "modules": self.module_manager.status_snapshot(),
            },
        )

    async def _handle_health_check(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            request = await asyncio.wait_for(reader.read(4096), timeout=2)
            parts = request.split(b"\r\n", 1)[0].split(b" ")
            path = parts[1] if len(parts) >= 2 else b"/"
            if path not in {b"/", b"/health", b"/ready"}:
                status_code, reason = 404, "Not Found"
                payload = {"status": "not_found"}
            else:
                status_code, payload = self.health_snapshot()
                reason = "OK" if status_code == 200 else "Service Unavailable"
            body = (json.dumps(payload, separators=(",", ":")) + "\n").encode()
            writer.write(
                (
                    f"HTTP/1.1 {status_code} {reason}\r\n"
                    "Content-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    "Connection: close\r\n\r\n"
                ).encode()
                + body
            )
            await writer.drain()
        except (TimeoutError, ConnectionError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    async def close(self) -> None:
        self.ready_event.clear()
        if self.health_server is not None:
            self.health_server.close()
            await self.health_server.wait_closed()
        await self.module_manager.shutdown()
        await super().close()


async def main() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)
    bot = WGGBot(settings)
    async with bot:
        await bot.start(settings.discord_token, reconnect=True)


if __name__ == "__main__":
    asyncio.run(main())
