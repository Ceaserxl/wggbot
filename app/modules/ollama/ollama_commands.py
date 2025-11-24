# modules/ollama/commands.py

import discord
from discord import app_commands
from .ollama_base import ask_ollama


def register(bot):
    """
    Registers: /ollama
    This command performs a simple hello-world test roundtrip.
    """

    @bot.tree.command(
        name="ollama",
        description="Test the Ollama server by sending a hello-world prompt."
    )
    async def ollama_test(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        prompt = "hello world"

        # Send to Ollama using core logic
        reply = await ask_ollama(prompt)

        # Discord safety
        reply = reply[:2000] if reply else "❌ No response from Ollama."

        await interaction.followup.send(reply)
