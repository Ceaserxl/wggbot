# app/modules/ollama/ollama_commands.py

import discord
from discord import app_commands

from app.core.config import cfg
from .ollama_base import ask_ollama


def register(bot):

    # -------------------------------------------------------
    # /test_ollama
    # -------------------------------------------------------
    @bot.tree.command(
        name="test_ollama",
        description="Test the Ollama server with a simple hello prompt."
    )
    async def test_ollama(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        reply = await ask_ollama("test connection")
        reply = reply[:2000] if reply else "❌ No response from Ollama."

        await interaction.followup.send(reply)

    # -------------------------------------------------------
    # Get available models from settings.ini
    # -------------------------------------------------------
    def get_available_models():
        raw = cfg("ollama", "available_models", "")
        return [m.strip() for m in raw.split(",") if m.strip()]

    # -------------------------------------------------------
    # Dynamic choices
    # -------------------------------------------------------
    def model_choices():
        lst = get_available_models()
        return (
            [app_commands.Choice(name=m, value=m) for m in lst]
            if lst else [app_commands.Choice(name="default", value="")]
        )

    # -------------------------------------------------------
    # /ollama prompt + optional model
    # -------------------------------------------------------
    @bot.tree.command(
        name="ollama",
        description="Ask the Ollama LLM with optional model override."
    )
    @app_commands.describe(
        prompt="Your message to the LLM",
        model="Choose a model (optional)"
    )
    @app_commands.choices(model=model_choices())
    async def ollama_cmd(
        interaction: discord.Interaction,
        prompt: str,
        model: app_commands.Choice[str] = None
    ):
        await interaction.response.defer(thinking=True)
        # Pass model.value if it exists, otherwise None
        chosen = model.value if model else None

        reply = await ask_ollama(prompt, chosen)
        reply = reply[:2000] if reply else "❌ No response from Ollama."

        await interaction.followup.send(reply)
