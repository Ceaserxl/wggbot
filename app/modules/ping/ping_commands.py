# modules/ping/ping_commands.py

import discord
from discord import app_commands
from .ping_base import ping_logic

def register(bot):

    @bot.tree.command(
        name="ping",
        description="Returns the bot's latency."
    )
    async def ping_cmd(interaction: discord.Interaction):
        # Delegate calculations to the fancy logic layer
        ms = ping_logic(bot)
        await interaction.response.send_message(
            f"🏓 Pong! `{ms:.2f} ms`"
        )
