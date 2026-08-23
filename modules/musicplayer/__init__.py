from __future__ import annotations

import asyncio
import logging
import math
from typing import Any, cast

import discord
from discord import app_commands
from discord.ext import commands

from .player import GuildPlayer, QueueFullError
from .sources import MediaResolutionError, MediaResolver

LOGGER = logging.getLogger(__name__)


class MusicCog(commands.GroupCog, group_name="music", group_description="Play and manage music"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings = cast(Any, bot).settings
        self.resolver = MediaResolver(self.settings)
        self.players: dict[int, GuildPlayer] = {}

    def player(self, guild_id: int) -> GuildPlayer:
        if guild_id not in self.players:
            self.players[guild_id] = GuildPlayer(guild_id, self.resolver, self.settings)
        return self.players[guild_id]

    @staticmethod
    async def _voice_channel(
        interaction: discord.Interaction,
    ) -> discord.VoiceChannel | discord.StageChannel:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            raise app_commands.CheckFailure("Music commands must be used in a server.")
        voice = interaction.user.voice
        if not voice or not voice.channel:
            raise app_commands.CheckFailure("Join a voice channel first.")
        guild_voice = interaction.guild.voice_client
        if guild_voice and guild_voice.channel != voice.channel:
            raise app_commands.CheckFailure("Join the bot's voice channel to control playback.")
        return voice.channel

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.CheckFailure):
            message = str(error)
        else:
            LOGGER.exception("Music command failed", exc_info=error)
            message = "The music command failed. Check the bot logs for details."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(
        name="play", description="Play a URL, playlist, Spotify link, or search query"
    )
    @app_commands.describe(
        query="Media URL or search terms", playlist_limit="Maximum playlist items to add"
    )
    @app_commands.checks.cooldown(
        2, 10, key=lambda interaction: (interaction.guild_id, interaction.user.id)
    )
    async def play(
        self,
        interaction: discord.Interaction,
        query: str,
        playlist_limit: app_commands.Range[int, 1, 200] = 25,
    ) -> None:
        channel = await self._voice_channel(interaction)
        await interaction.response.defer(thinking=True)
        limit = min(playlist_limit, self.settings.music_max_playlist)
        try:
            tracks = await self.resolver.resolve(
                query, interaction.user.id, interaction.user.mention, limit
            )
            guild_id = interaction.guild_id
            text_channel = interaction.channel
            if guild_id is None or not isinstance(text_channel, discord.abc.Messageable):
                raise app_commands.CheckFailure("Music commands must be used in a server channel.")
            player = self.player(guild_id)
            player.bind(channel, text_channel)
            player.enqueue(tracks)
        except (MediaResolutionError, QueueFullError) as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        source_note = (
            " Spotify metadata will be matched to a playable source."
            if query.startswith("https://open.spotify.com/")
            else ""
        )
        await interaction.followup.send(
            f"Queued **{len(tracks)}** track{'s' if len(tracks) != 1 else ''}.{source_note}",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="now", description="Show the current track")
    async def now(self, interaction: discord.Interaction) -> None:
        player = self.players.get(interaction.guild_id or 0)
        track = player.current if player else None
        if not track:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"▶️ **{discord.utils.escape_markdown(track.label)}** `{track.duration_label}`\n"
            f"Requested by {track.requester_mention} · {discord.utils.escape_markdown(track.source)}",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="queue", description="Show a page of the queue")
    async def queue(
        self, interaction: discord.Interaction, page: app_commands.Range[int, 1, 100] = 1
    ) -> None:
        player = self.players.get(interaction.guild_id or 0)
        if not player or (not player.current and not player.queue):
            await interaction.response.send_message("The queue is empty.", ephemeral=True)
            return
        per_page = 10
        pages = max(1, math.ceil(len(player.queue) / per_page))
        page = min(page, pages)
        start = (page - 1) * per_page
        entries = list(player.queue)[start : start + per_page]
        lines = [
            f"`{start + index}.` {discord.utils.escape_markdown(track.label)} `{track.duration_label}`"
            for index, track in enumerate(entries, 1)
        ]
        now = discord.utils.escape_markdown(player.current.label) if player.current else "Nothing"
        await interaction.response.send_message(
            f"**Now:** {now}\n\n"
            + ("\n".join(lines) or "No upcoming tracks.")
            + f"\n\nPage {page}/{pages}",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def _control(self, interaction: discord.Interaction) -> GuildPlayer:
        await self._voice_channel(interaction)
        player = self.players.get(interaction.guild_id or 0)
        if not player:
            raise app_commands.CheckFailure("There is no active player in this server.")
        return player

    @app_commands.command(name="pause", description="Pause playback")
    async def pause(self, interaction: discord.Interaction) -> None:
        player = await self._control(interaction)
        await interaction.response.send_message(
            "Paused." if player.pause() else "Nothing is playing.", ephemeral=True
        )

    @app_commands.command(name="resume", description="Resume playback")
    async def resume(self, interaction: discord.Interaction) -> None:
        player = await self._control(interaction)
        await interaction.response.send_message(
            "Resumed." if player.resume() else "Playback is not paused.", ephemeral=True
        )

    @app_commands.command(name="skip", description="Skip the current track")
    async def skip(self, interaction: discord.Interaction) -> None:
        player = await self._control(interaction)
        await interaction.response.send_message(
            "Skipped." if player.skip() else "Nothing is playing.", ephemeral=True
        )

    @app_commands.command(name="stop", description="Stop playback and clear the queue")
    async def stop(self, interaction: discord.Interaction) -> None:
        player = await self._control(interaction)
        removed = player.clear()
        player.skip()
        await interaction.response.send_message(f"Stopped and removed {removed} queued tracks.")

    @app_commands.command(name="disconnect", description="Disconnect and clear the queue")
    async def disconnect(self, interaction: discord.Interaction) -> None:
        player = await self._control(interaction)
        await player.disconnect()
        await interaction.response.send_message("Disconnected and cleared the queue.")

    @app_commands.command(
        name="clear", description="Clear upcoming tracks without stopping the current one"
    )
    async def clear(self, interaction: discord.Interaction) -> None:
        player = await self._control(interaction)
        await interaction.response.send_message(f"Removed {player.clear()} queued tracks.")

    @app_commands.command(name="remove", description="Remove one queued track")
    async def remove(self, interaction: discord.Interaction, position: int) -> None:
        player = await self._control(interaction)
        try:
            track = player.remove(position)
        except IndexError as exc:
            raise app_commands.CheckFailure(str(exc)) from exc
        await interaction.response.send_message(
            f"Removed **{discord.utils.escape_markdown(track.label)}**."
        )

    @app_commands.command(name="move", description="Move a queued track to another position")
    async def move(self, interaction: discord.Interaction, position: int, destination: int) -> None:
        player = await self._control(interaction)
        try:
            track = player.move(position, destination)
        except IndexError as exc:
            raise app_commands.CheckFailure(str(exc)) from exc
        await interaction.response.send_message(
            f"Moved **{discord.utils.escape_markdown(track.label)}** to position {destination}."
        )

    @app_commands.command(name="shuffle", description="Shuffle upcoming tracks")
    async def shuffle(self, interaction: discord.Interaction) -> None:
        player = await self._control(interaction)
        await interaction.response.send_message(f"Shuffled {player.shuffle()} queued tracks.")

    @app_commands.command(name="volume", description="Set playback volume")
    async def volume(
        self, interaction: discord.Interaction, percent: app_commands.Range[int, 0, 200]
    ) -> None:
        player = await self._control(interaction)
        player.set_volume(percent)
        await interaction.response.send_message(f"Volume set to {percent}%.")

    @app_commands.command(name="repeat", description="Set repeat mode")
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Off", value="off"),
            app_commands.Choice(name="Current track", value="one"),
            app_commands.Choice(name="Entire queue", value="all"),
        ]
    )
    async def repeat(
        self, interaction: discord.Interaction, mode: app_commands.Choice[str]
    ) -> None:
        player = await self._control(interaction)
        player.repeat_mode = mode.value
        await interaction.response.send_message(f"Repeat mode set to **{mode.name}**.")

    @app_commands.command(name="history", description="Show recently played tracks")
    async def history(self, interaction: discord.Interaction) -> None:
        player = self.players.get(interaction.guild_id or 0)
        tracks = list(player.history)[:10] if player else []
        if not tracks:
            await interaction.response.send_message(
                "No playback history is available.", ephemeral=True
            )
            return
        lines = [
            f"`{index}.` {discord.utils.escape_markdown(track.label)}"
            for index, track in enumerate(tracks, 1)
        ]
        await interaction.response.send_message(
            "\n".join(lines), allowed_mentions=discord.AllowedMentions.none()
        )

    @app_commands.command(name="sources", description="Show configured playback sources")
    async def sources(self, interaction: discord.Interaction) -> None:
        spotify = bool(self.settings.spotify_client_id and self.settings.spotify_client_secret)
        cookies = self.resolver.cookie_available
        await interaction.response.send_message(
            "Search and yt-dlp-supported URLs: **ready**\n"
            f"YouTube subscription cookie: **{'ready' if cookies else 'not mounted'}**\n"
            f"Spotify metadata matching: **{'ready' if spotify else 'not configured'}**",
            ephemeral=True,
        )

    async def close(self) -> None:
        await asyncio.gather(
            *(player.close() for player in self.players.values()), return_exceptions=True
        )
        await self.resolver.close()


async def setup(bot: commands.Bot) -> None:
    cog = MusicCog(bot)
    cast(Any, bot)._wgg_music_cog = cog
    await bot.add_cog(cog)


async def teardown(bot: commands.Bot) -> None:
    cog = getattr(bot, "_wgg_music_cog", None)
    if cog:
        await cog.close()
        del cast(Any, bot)._wgg_music_cog
