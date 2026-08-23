from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ModuleDefinition:
    name: str
    extension: str
    description: str
    default_enabled: bool


MODULES: dict[str, ModuleDefinition] = {
    "musicplayer": ModuleDefinition(
        "musicplayer", "modules.musicplayer", "Voice playback and media queues", True
    ),
    "ollama": ModuleDefinition("ollama", "modules.ollama", "Local Ollama chat integration", True),
    "stablediffusion": ModuleDefinition(
        "stablediffusion", "modules.stablediffusion", "ComfyUI image generation", False
    ),
}


class ModuleManager:
    def __init__(self, bot: commands.Bot, state_path: Path):
        self.bot = bot
        self.state_path = state_path
        self._enabled = self._read_state()
        self._errors: dict[str, str] = {}
        self._lock = asyncio.Lock()

    def _read_state(self) -> dict[str, bool]:
        state = {name: module.default_enabled for name, module in MODULES.items()}
        if not self.state_path.exists():
            return state
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            for name, enabled in raw.get("enabled", {}).items():
                if name in MODULES and isinstance(enabled, bool):
                    state[name] = enabled
        except (OSError, ValueError, TypeError):
            LOGGER.exception("Could not read module state; using defaults")
        return state

    def _write_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"enabled": self._enabled}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.state_path)

    def definition(self, name: str) -> ModuleDefinition:
        try:
            return MODULES[name.lower()]
        except KeyError as exc:
            raise ValueError(f"Unknown module {name!r}") from exc

    def is_loaded(self, name: str) -> bool:
        return self.definition(name).extension in self.bot.extensions

    async def load_enabled(self) -> None:
        for name, enabled in self._enabled.items():
            if enabled:
                try:
                    await self._load(name)
                except commands.ExtensionError as exc:
                    self._errors[name] = f"{type(exc).__name__}: {exc}"
                    LOGGER.exception("Failed to load module %s", name)
        self._write_state()

    async def _load(self, name: str) -> None:
        module = self.definition(name)
        await self.bot.load_extension(module.extension)
        self._errors.pop(name, None)
        LOGGER.info("Loaded module %s", name)

    async def enable(self, name: str) -> None:
        async with self._lock:
            module = self.definition(name)
            if module.extension not in self.bot.extensions:
                await self._load(name)
            self._enabled[name] = True
            self._write_state()

    async def disable(self, name: str) -> None:
        async with self._lock:
            module = self.definition(name)
            if module.extension in self.bot.extensions:
                await self.bot.unload_extension(module.extension)
            self._enabled[name] = False
            self._errors.pop(name, None)
            self._write_state()
            LOGGER.info("Disabled module %s", name)

    async def reload(self, name: str) -> None:
        async with self._lock:
            module = self.definition(name)
            if module.extension in self.bot.extensions:
                await self.bot.reload_extension(module.extension)
            else:
                await self._load(name)
            self._enabled[name] = True
            self._errors.pop(name, None)
            self._write_state()
            LOGGER.info("Reloaded module %s", name)

    async def sync_commands(self) -> int:
        return len(await self.bot.tree.sync())

    def status_snapshot(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for name in MODULES:
            if name in self._errors:
                result[name] = "error"
            elif self.is_loaded(name):
                result[name] = "loaded"
            else:
                result[name] = "disabled"
        return result

    async def shutdown(self) -> None:
        for module in reversed(tuple(MODULES.values())):
            if module.extension in self.bot.extensions:
                try:
                    await self.bot.unload_extension(module.extension)
                except commands.ExtensionError:
                    LOGGER.exception("Failed to unload %s during shutdown", module.name)


class ModulesCog(commands.GroupCog, group_name="modules", group_description="Manage bot modules"):
    def __init__(self, bot: commands.Bot, manager: ModuleManager):
        self.bot = bot
        self.manager = manager

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if await self.bot.is_owner(interaction.user):
            return True
        await interaction.response.send_message(
            "Only the bot owner can manage modules.", ephemeral=True
        )
        return False

    async def _finish(self, interaction: discord.Interaction, message: str) -> None:
        synced = await self.manager.sync_commands()
        await interaction.followup.send(f"{message} Synced {synced} commands.", ephemeral=True)

    @app_commands.command(name="list", description="Show available modules and their state")
    async def list_modules(self, interaction: discord.Interaction) -> None:
        states = self.manager.status_snapshot()
        lines = [
            f"**{name}** — `{states[name]}` — {definition.description}"
            for name, definition in MODULES.items()
        ]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="enable", description="Enable and load a module")
    async def enable_module(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            await self.manager.enable(name.lower())
            await self._finish(interaction, f"Enabled `{name.lower()}`.")
        except (ValueError, commands.ExtensionError) as exc:
            LOGGER.exception("Module enable failed")
            await interaction.followup.send(
                f"Could not enable `{name}`: {type(exc).__name__}", ephemeral=True
            )

    @app_commands.command(name="disable", description="Disable and unload a module")
    async def disable_module(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            await self.manager.disable(name.lower())
            await self._finish(interaction, f"Disabled `{name.lower()}`.")
        except (ValueError, commands.ExtensionError) as exc:
            LOGGER.exception("Module disable failed")
            await interaction.followup.send(
                f"Could not disable `{name}`: {type(exc).__name__}", ephemeral=True
            )

    @app_commands.command(name="reload", description="Reload a module without restarting the bot")
    async def reload_module(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            await self.manager.reload(name.lower())
            await self._finish(interaction, f"Reloaded `{name.lower()}`.")
        except (ValueError, commands.ExtensionError) as exc:
            LOGGER.exception("Module reload failed")
            await interaction.followup.send(
                f"Could not reload `{name}`: {type(exc).__name__}", ephemeral=True
            )

    @enable_module.autocomplete("name")
    @disable_module.autocomplete("name")
    @reload_module.autocomplete("name")
    async def module_names(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        del interaction
        return [
            app_commands.Choice(name=name, value=name)
            for name in MODULES
            if current.lower() in name
        ][:25]
