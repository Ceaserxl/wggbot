# modules/musicplayer/commands.py

import discord
from discord import app_commands

from .musicplayer import (
    handle_play_command,
    handle_playlist_command,
    handle_disconnect_command,
    handle_skip_command,
    handle_queue_command,
)


# -------------------------------------------------------------------
# setup(bot) — loader.py will import this
# -------------------------------------------------------------------
def setup(bot):

    # ============================================================
    # /play
    # ============================================================
    @bot.tree.command(
        name="play",
        description="Play a song from a YouTube link."
    )
    async def play(interaction: discord.Interaction, link: str):

        if isinstance(interaction.channel, discord.DMChannel):
            await interaction.response.send_message(
                "This command cannot be used in DMs.",
                ephemeral=True
            )
            return

        await interaction.response.defer()
        msg = await interaction.followup.send("Fetching song info...")

        try:
            await handle_play_command(interaction, link, msg)
        except Exception as e:
            await msg.edit(content=f"Error: {str(e)}")



    # ============================================================
    # /playlist
    # ============================================================
    @bot.tree.command(
        name="playlist",
        description="Play a playlist from a YouTube link."
    )
    async def playlist(
        interaction: discord.Interaction,
        link: str,
        songs: int = 5
    ):

        if isinstance(interaction.channel, discord.DMChannel):
            await interaction.response.send_message(
                "This command cannot be used in DMs.",
                ephemeral=True
            )
            return

        await interaction.response.defer()
        msg = await interaction.followup.send("Fetching playlist info...")

        try:
            await handle_playlist_command(interaction, link, songs, msg)
        except Exception as e:
            await msg.edit(content=f"Error: {str(e)}")



    # ============================================================
    # /skip
    # ============================================================
    @bot.tree.command(
        name="skip",
        description="Skip the currently playing song."
    )
    async def skip(interaction: discord.Interaction):

        if isinstance(interaction.channel, discord.DMChannel):
            await interaction.response.send_message(
                "This command cannot be used in DMs.",
                ephemeral=True
            )
            return

        await interaction.response.defer()
        await handle_skip_command(interaction)



    # ============================================================
    # /queue
    # ============================================================
    @bot.tree.command(
        name="queue",
        description="Show the current song queue."
    )
    async def queue(interaction: discord.Interaction):

        if isinstance(interaction.channel, discord.DMChannel):
            await interaction.response.send_message(
                "This command cannot be used in DMs.",
                ephemeral=True
            )
            return

        await interaction.response.defer()
        await handle_queue_command(interaction)



    # ============================================================
    # /disconnect
    # ============================================================
    @bot.tree.command(
        name="disconnect",
        description="Disconnect the bot from the voice channel."
    )
    async def disconnect(interaction: discord.Interaction):

        if isinstance(interaction.channel, discord.DMChannel):
            await interaction.response.send_message(
                "This command cannot be used in DMs.",
                ephemeral=True
            )
            return

        await interaction.response.defer()
        await handle_disconnect_command(interaction)
