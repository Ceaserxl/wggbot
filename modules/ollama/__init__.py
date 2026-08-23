from __future__ import annotations

import logging
from typing import Any, cast

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

LOGGER = logging.getLogger(__name__)


def _chunks(value: str, size: int = 1900) -> list[str]:
    if not value:
        return ["(empty response)"]
    return [value[index : index + size] for index in range(0, len(value), size)][:5]


class OllamaCog(
    commands.GroupCog, group_name="ollama", group_description="Use the local Ollama service"
):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings = cast(Any, bot).settings
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120))

    async def _models(self) -> list[str]:
        try:
            async with self.session.get(f"{self.settings.ollama_url}/api/tags") as response:
                if response.status != 200:
                    return []
                data = await response.json()
            return [str(model["name"]) for model in data.get("models", []) if model.get("name")]
        except (aiohttp.ClientError, TimeoutError):
            return []

    async def _ask(self, prompt: str, model: str | None) -> str:
        payload = {
            "model": model or self.settings.ollama_model,
            "prompt": prompt,
            "stream": False,
        }
        try:
            async with self.session.post(
                f"{self.settings.ollama_url}/api/generate", json=payload
            ) as response:
                if response.status != 200:
                    LOGGER.warning("Ollama returned HTTP %s", response.status)
                    raise RuntimeError("Ollama is unavailable right now.")
                data = await response.json()
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise RuntimeError("Ollama is unavailable right now.") from exc
        return str(data.get("response") or "").strip()

    @app_commands.command(name="ask", description="Send a prompt to Ollama")
    @app_commands.describe(prompt="Prompt for the model", model="Optional installed model name")
    @app_commands.checks.cooldown(
        2, 30, key=lambda interaction: (interaction.guild_id, interaction.user.id)
    )
    async def ask(
        self,
        interaction: discord.Interaction,
        prompt: app_commands.Range[str, 1, 4000],
        model: str | None = None,
    ) -> None:
        await interaction.response.defer(thinking=True)
        try:
            reply = await self._ask(prompt, model)
        except RuntimeError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        for chunk in _chunks(reply):
            await interaction.followup.send(chunk, allowed_mentions=discord.AllowedMentions.none())

    @ask.autocomplete("model")
    async def model_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        del interaction
        models = await self._models()
        return [
            app_commands.Choice(name=model[:100], value=model[:100])
            for model in models
            if current.lower() in model.lower()
        ][:25]

    @app_commands.command(name="models", description="List models reported by Ollama")
    async def models(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        models = await self._models()
        if not models:
            await interaction.followup.send(
                "Ollama is unavailable or has no installed models.", ephemeral=True
            )
            return
        await interaction.followup.send(
            "\n".join(f"• `{model}`" for model in models[:50]), ephemeral=True
        )

    async def close(self) -> None:
        await self.session.close()


async def setup(bot: commands.Bot) -> None:
    cog = OllamaCog(bot)
    cast(Any, bot)._wgg_ollama_cog = cog
    await bot.add_cog(cog)


async def teardown(bot: commands.Bot) -> None:
    cog = getattr(bot, "_wgg_ollama_cog", None)
    if cog:
        await cog.close()
        del cast(Any, bot)._wgg_ollama_cog
