from __future__ import annotations

import asyncio
import io
import json
import logging
import random
from pathlib import Path
from typing import Any, cast

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

LOGGER = logging.getLogger(__name__)
WORKFLOW_PATH = Path(__file__).resolve().parent / "workflows" / "default.json"


class ComfyUIError(RuntimeError):
    pass


class StableDiffusionCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.host = cast(Any, bot).settings.comfyui_url
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=600))

    @staticmethod
    def _workflow(prompt: str) -> tuple[dict[str, Any], str]:
        graph = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
        save_node = ""
        for node_id, node in graph.items():
            inputs = node.get("inputs", {})
            if node_id == "56" and "value" in inputs:
                inputs["value"] = prompt
            if node_id == "155" and "value" in inputs:
                inputs["value"] = random.SystemRandom().randint(1, 2_147_483_647)
            if node.get("class_type") == "SaveImage":
                save_node = node_id
        if not save_node:
            raise ComfyUIError("The configured workflow has no SaveImage node.")
        return graph, save_node

    async def _generate(self, prompt: str) -> bytes:
        graph, save_node = self._workflow(prompt)
        try:
            async with self.session.post(
                f"{self.host}/prompt", json={"prompt": graph, "client_id": "wggbot-discord"}
            ) as response:
                if response.status != 200:
                    raise ComfyUIError(
                        f"ComfyUI rejected the workflow with HTTP {response.status}."
                    )
                data = await response.json()
            prompt_id = data.get("prompt_id")
            if not prompt_id:
                raise ComfyUIError("ComfyUI did not return a prompt ID.")

            deadline = asyncio.get_running_loop().time() + 300
            history: dict[str, Any] | None = None
            while asyncio.get_running_loop().time() < deadline:
                async with self.session.get(f"{self.host}/history/{prompt_id}") as response:
                    if response.status == 200:
                        payload = await response.json()
                        if prompt_id in payload and "outputs" in payload[prompt_id]:
                            history = payload[prompt_id]
                            break
                    elif response.status != 404:
                        raise ComfyUIError(f"ComfyUI history returned HTTP {response.status}.")
                await asyncio.sleep(1)
            if history is None:
                raise ComfyUIError("Image generation timed out.")

            images = history.get("outputs", {}).get(str(save_node), {}).get("images", [])
            if not images:
                raise ComfyUIError("The workflow completed without an image.")
            image = images[0]
            params = {
                "filename": image["filename"],
                "subfolder": image.get("subfolder", ""),
                "type": image.get("type", "output"),
            }
            async with self.session.get(f"{self.host}/view", params=params) as response:
                if response.status != 200:
                    raise ComfyUIError(f"ComfyUI image download returned HTTP {response.status}.")
                content = await response.read()
            if len(content) > 25 * 1024 * 1024:
                raise ComfyUIError("The generated image exceeds Discord's 25 MB upload limit.")
            return content
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise ComfyUIError("ComfyUI is unavailable right now.") from exc

    @app_commands.command(
        name="imagine", description="Generate an image with the configured ComfyUI workflow"
    )
    @app_commands.describe(prompt="Description of the image to generate")
    @app_commands.checks.cooldown(
        1, 60, key=lambda interaction: (interaction.guild_id, interaction.user.id)
    )
    async def imagine(
        self, interaction: discord.Interaction, prompt: app_commands.Range[str, 1, 1000]
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("Use this command in a server.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        try:
            content = await self._generate(prompt)
        except (ComfyUIError, OSError, ValueError, KeyError):
            LOGGER.exception("Image generation failed")
            await interaction.followup.send(
                "Image generation failed. Check the bot logs for details.", ephemeral=True
            )
            return
        await interaction.followup.send(
            f"🖼️ **Prompt:** {discord.utils.escape_markdown(prompt)}",
            file=discord.File(io.BytesIO(content), filename="generated-image.png"),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def close(self) -> None:
        await self.session.close()


async def setup(bot: commands.Bot) -> None:
    cog = StableDiffusionCog(bot)
    cast(Any, bot)._wgg_stablediffusion_cog = cog
    await bot.add_cog(cog)


async def teardown(bot: commands.Bot) -> None:
    cog = getattr(bot, "_wgg_stablediffusion_cog", None)
    if cog:
        await cog.close()
        del cast(Any, bot)._wgg_stablediffusion_cog
