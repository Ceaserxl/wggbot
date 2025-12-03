# /app/modules/musicplayer/musicplayer_commands.py

import discord
from discord import app_commands

from .musicplayer_base import (
    handle_play,
    handle_playlist,
    handle_skip,
    handle_queue,
    handle_disconnect,
)
print("WHAT THE FUCK")
# -------------------------------------------------------------
# register(bot)
# Called automatically by module_loader after init()
# -------------------------------------------------------------
def register(bot):
    # ==========================================================
    # /play
    # ==========================================================
    @bot.tree.command(
        name="play",
        description="Play a song from a YouTube link."
    )
    async def play_cmd(interaction: discord.Interaction, link: str):

        if isinstance(interaction.channel, discord.DMChannel):
            return await interaction.response.send_message(
                "❌ This command cannot be used in DMs.",
                ephemeral=True
            )

        await interaction.response.defer()
        msg = await interaction.followup.send("🎵 Fetching song info...")

        try:
            await handle_play(interaction, link, msg)
        except Exception as e:
            await msg.edit(content=f"❌ Error: {e}")


    # ==========================================================
    # /playlist
    # ==========================================================
    @bot.tree.command(
        name="playlist",
        description="Queue multiple songs from a YouTube playlist."
    )
    async def playlist_cmd(
        interaction: discord.Interaction,
        link: str,
        songs: int = 5
    ):

        if isinstance(interaction.channel, discord.DMChannel):
            return await interaction.response.send_message(
                "❌ This command cannot be used in DMs.",
                ephemeral=True
            )

        await interaction.response.defer()
        msg = await interaction.followup.send("📀 Loading playlist...")

        try:
            await handle_playlist(interaction, link, songs, msg)
        except Exception as e:
            await msg.edit(content=f"❌ Error: {e}")


    # ==========================================================
    # /skip
    # ==========================================================
    @bot.tree.command(
        name="skip",
        description="Skip the currently playing track."
    )
    async def skip_cmd(interaction: discord.Interaction):

        if isinstance(interaction.channel, discord.DMChannel):
            return await interaction.response.send_message(
                "❌ This command cannot be used in DMs.",
                ephemeral=True
            )

        await interaction.response.defer()
        await handle_skip(interaction)


    # ==========================================================
    # /queue
    # ==========================================================
    @bot.tree.command(
        name="queue",
        description="Show the current song queue."
    )
    async def queue_cmd(interaction: discord.Interaction):

        if isinstance(interaction.channel, discord.DMChannel):
            return await interaction.response.send_message(
                "❌ This command cannot be used in DMs.",
                ephemeral=True
            )

        await interaction.response.defer()
        await handle_queue(interaction)


    # ==========================================================
    # /disconnect
    # ==========================================================
    @bot.tree.command(
        name="disconnect",
        description="Disconnect the bot from the voice channel."
    )
    async def disconnect_cmd(interaction: discord.Interaction):

        if isinstance(interaction.channel, discord.DMChannel):
            return await interaction.response.send_message(
                "❌ This command cannot be used in DMs.",
                ephemeral=True
            )

        await interaction.response.defer()
        await handle_disconnect(interaction)
