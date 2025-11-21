# modules/ollama/commands.py

import discord
from discord import app_commands

from .ollama import (
    query_ollama,
    handle_ollama_response,
    SYSTEM_CONTEXT,
    CHAT_LIMIT
)


# -------------------------------------------------------------------
# setup(bot) — loaded dynamically by main.py
# -------------------------------------------------------------------
def setup(bot):

    # ================================================================
    # /ollama — Direct Ollama prompt (non-threaded)
    # ================================================================
    @bot.tree.command(
        name="ollama",
        description="Ask the local Ollama AI a question."
    )
    @app_commands.describe(
        prompt="What you want to ask Ollama",
        model="Model name (optional, defaults to your config)"
    )
    async def ollama_cmd(
        interaction: discord.Interaction,
        prompt: str,
        model: str = None
    ):
        await interaction.response.defer(thinking=True)

        # Build a simple one-shot prompt
        formatted_prompt = (
            f"{SYSTEM_CONTEXT}\n\n"
            f"User: {prompt}\n"
            "Bot:"
        )

        result = await query_ollama(
            formatted_prompt,
            model=model if model else None
        )

        # Discord limit protection
        result = result[:2000]

        await interaction.followup.send(result)



    # ================================================================
    # Auto-thread Ollama response (global handler in main.py)
    # ================================================================
    # NOTE:
    # This handler stays in main.py because it needs global visibility.
    # We just expose the function from this module.
    pass
