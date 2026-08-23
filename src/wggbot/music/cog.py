from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

import discord
from discord import app_commands
from discord.ext import commands

from .models import Track
from .player import GuildPlayer, QueueFullError
from .presentation import (
    history_embed,
    now_playing_embed,
    queue_embed,
    queued_embed,
    sources_embed,
    status_embed,
)
from .resolver import MediaResolutionError, MediaResolver
from .ui import PlaybackControls, QueueControls

LOGGER = logging.getLogger(__name__)


class MusicCog(commands.GroupCog, group_name="music", group_description="Play and manage music"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings = cast(Any, bot).settings
        self.resolver = MediaResolver(self.settings)
        self.players: dict[int, GuildPlayer] = {}

    def player(self, guild_id: int) -> GuildPlayer:
        if guild_id not in self.players:
            self.players[guild_id] = GuildPlayer(
                guild_id,
                self.resolver,
                self.settings,
                on_track_start=self._announce_track,
            )
        return self.players[guild_id]

    @staticmethod
    async def _voice_channel(
        interaction: discord.Interaction,
    ) -> discord.VoiceChannel | discord.StageChannel:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            raise app_commands.CheckFailure("Music controls must be used in a server.")
        voice = interaction.user.voice
        if not voice or not voice.channel:
            raise app_commands.CheckFailure("Join a voice channel first.")
        guild_voice = interaction.guild.voice_client
        if guild_voice and guild_voice.channel != voice.channel:
            raise app_commands.CheckFailure("Join the bot's voice channel to control playback.")
        return voice.channel

    async def can_control(self, interaction: discord.Interaction) -> bool:
        try:
            await self._voice_channel(interaction)
            return True
        except app_commands.CheckFailure as error:
            await interaction.response.send_message(
                embed=status_embed("Control unavailable", str(error), error=True),
                ephemeral=True,
            )
            return False

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.CommandOnCooldown):
            message = f"Try again in **{error.retry_after:.1f} seconds**."
        elif isinstance(error, app_commands.CheckFailure):
            message = str(error)
        else:
            LOGGER.exception("Music command failed", exc_info=error)
            message = "That command failed unexpectedly. The details are in the bot log."
        embed = status_embed("Music command unavailable", message, error=True)
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _announce_track(self, player: GuildPlayer, track: Track) -> None:
        del track
        if player.text_channel is None:
            return
        view = PlaybackControls(self, player)
        message = await player.text_channel.send(
            embed=now_playing_embed(player),
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        view.attach(message)

    async def send_queue(
        self,
        interaction: discord.Interaction,
        player: GuildPlayer,
        *,
        ephemeral: bool,
        page: int = 0,
    ) -> None:
        embed, page, _ = queue_embed(player, page)
        view = QueueControls(self, player, page)
        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=ephemeral,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        view.attach(await interaction.original_response())

    async def _control(self, interaction: discord.Interaction) -> GuildPlayer:
        await self._voice_channel(interaction)
        player = self.players.get(interaction.guild_id or 0)
        if not player:
            raise app_commands.CheckFailure("There is no active player in this server.")
        return player

    @app_commands.command(
        name="play",
        description="Play a search, URL, playlist, or Spotify link",
    )
    @app_commands.describe(
        query="Song, artist, or media URL",
        playlist_limit="Maximum tracks to add from a playlist",
    )
    @app_commands.checks.cooldown(
        2,
        10,
        key=lambda interaction: (interaction.guild_id, interaction.user.id),
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
                query,
                interaction.user.id,
                interaction.user.mention,
                limit,
            )
            guild_id = interaction.guild_id
            text_channel = interaction.channel
            if guild_id is None or not isinstance(text_channel, discord.abc.Messageable):
                raise app_commands.CheckFailure("Music must be used in a server text channel.")
            player = self.player(guild_id)
            player.bind(channel, text_channel)
            player.enqueue(tracks)
        except (MediaResolutionError, QueueFullError) as error:
            await interaction.followup.send(
                embed=status_embed("Could not add that", str(error), error=True),
                ephemeral=True,
            )
            return

        view = QueueControls(self, player)
        message = await interaction.followup.send(
            embed=queued_embed(tracks, len(player.queue)),
            view=view,
            wait=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        view.attach(message)

    @app_commands.command(name="now", description="Open the current playback controls")
    async def now(self, interaction: discord.Interaction) -> None:
        player = self.players.get(interaction.guild_id or 0)
        if not player or not player.current:
            await interaction.response.send_message(
                embed=status_embed(
                    "Nothing playing",
                    "Start something with `/music play`.",
                ),
                ephemeral=True,
            )
            return
        view = PlaybackControls(self, player)
        await interaction.response.send_message(
            embed=now_playing_embed(player),
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        view.attach(await interaction.original_response())

    @app_commands.command(name="queue", description="Open the interactive music queue")
    async def queue(
        self,
        interaction: discord.Interaction,
        page: app_commands.Range[int, 1, 100] = 1,
    ) -> None:
        player = self.players.get(interaction.guild_id or 0)
        if not player:
            await interaction.response.send_message(
                embed=status_embed(
                    "Queue is empty",
                    "Add music with `/music play` and it will appear here.",
                ),
                ephemeral=True,
            )
            return
        await self.send_queue(interaction, player, ephemeral=False, page=page - 1)

    @app_commands.command(name="pause", description="Pause playback")
    async def pause(self, interaction: discord.Interaction) -> None:
        player = await self._control(interaction)
        changed = player.pause()
        await interaction.response.send_message(
            embed=status_embed(
                "Playback paused" if changed else "Nothing to pause",
                "Use `/music resume` or the play/pause button to continue."
                if changed
                else "No track is currently playing.",
                success=changed,
            ),
            ephemeral=True,
        )

    @app_commands.command(name="resume", description="Resume playback")
    async def resume(self, interaction: discord.Interaction) -> None:
        player = await self._control(interaction)
        changed = player.resume()
        await interaction.response.send_message(
            embed=status_embed(
                "Playback resumed" if changed else "Nothing to resume",
                "The current track is playing again." if changed else "Playback is not paused.",
                success=changed,
            ),
            ephemeral=True,
        )

    @app_commands.command(name="skip", description="Skip the current track")
    async def skip(self, interaction: discord.Interaction) -> None:
        player = await self._control(interaction)
        track = player.current
        skipped = player.skip()
        await interaction.response.send_message(
            embed=status_embed(
                "Track skipped" if skipped else "Nothing to skip",
                f"Skipped **{track.label}**." if skipped and track else "No track is playing.",
                success=skipped,
            )
        )

    @app_commands.command(name="stop", description="Stop playback and clear the queue")
    async def stop(self, interaction: discord.Interaction) -> None:
        player = await self._control(interaction)
        removed = player.clear()
        player.skip()
        await interaction.response.send_message(
            embed=status_embed(
                "Playback stopped",
                f"Stopped playback and removed **{removed}** queued tracks.",
                success=True,
            )
        )

    @app_commands.command(name="disconnect", description="Leave voice and clear the queue")
    async def disconnect(self, interaction: discord.Interaction) -> None:
        player = await self._control(interaction)
        await player.disconnect()
        await interaction.response.send_message(
            embed=status_embed(
                "Disconnected",
                "Left voice and cleared the queue.",
                success=True,
            )
        )

    @app_commands.command(name="clear", description="Clear upcoming tracks")
    async def clear(self, interaction: discord.Interaction) -> None:
        player = await self._control(interaction)
        removed = player.clear()
        await interaction.response.send_message(
            embed=status_embed(
                "Queue cleared",
                f"Removed **{removed}** upcoming tracks. The current track keeps playing.",
                success=True,
            )
        )

    @app_commands.command(name="remove", description="Remove one track from the queue")
    async def remove(self, interaction: discord.Interaction, position: int) -> None:
        player = await self._control(interaction)
        try:
            track = player.remove(position)
        except IndexError as error:
            raise app_commands.CheckFailure(str(error)) from error
        await interaction.response.send_message(
            embed=status_embed(
                "Track removed",
                f"Removed **{track.label}** from position `{position}`.",
                success=True,
            )
        )

    @app_commands.command(name="move", description="Move a queued track")
    async def move(self, interaction: discord.Interaction, position: int, destination: int) -> None:
        player = await self._control(interaction)
        try:
            track = player.move(position, destination)
        except IndexError as error:
            raise app_commands.CheckFailure(str(error)) from error
        await interaction.response.send_message(
            embed=status_embed(
                "Track moved",
                f"Moved **{track.label}** to position `{destination}`.",
                success=True,
            )
        )

    @app_commands.command(name="shuffle", description="Shuffle upcoming tracks")
    async def shuffle(self, interaction: discord.Interaction) -> None:
        player = await self._control(interaction)
        count = player.shuffle()
        await interaction.response.send_message(
            embed=status_embed(
                "Queue shuffled",
                f"Shuffled **{count}** upcoming tracks.",
                success=True,
            )
        )

    @app_commands.command(name="volume", description="Set playback volume")
    async def volume(
        self,
        interaction: discord.Interaction,
        percent: app_commands.Range[int, 0, 200],
    ) -> None:
        player = await self._control(interaction)
        player.set_volume(percent)
        await interaction.response.send_message(
            embed=status_embed(
                "Volume updated",
                f"Playback volume is now **{percent}%**.",
                success=True,
            ),
            ephemeral=True,
        )

    @app_commands.command(name="repeat", description="Set the loop mode")
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Off", value="off"),
            app_commands.Choice(name="Current track", value="one"),
            app_commands.Choice(name="Entire queue", value="all"),
        ]
    )
    async def repeat(
        self,
        interaction: discord.Interaction,
        mode: app_commands.Choice[str],
    ) -> None:
        player = await self._control(interaction)
        player.repeat_mode = mode.value
        await interaction.response.send_message(
            embed=status_embed(
                "Loop mode updated",
                f"Loop is now set to **{mode.name}**.",
                success=True,
            ),
            ephemeral=True,
        )

    @app_commands.command(name="history", description="Show recently played tracks")
    async def history(self, interaction: discord.Interaction) -> None:
        player = self.players.get(interaction.guild_id or 0)
        tracks = list(player.history)[:10] if player else []
        if not tracks:
            await interaction.response.send_message(
                embed=status_embed(
                    "No recent tracks",
                    "Playback history will appear after the first song finishes.",
                ),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=history_embed(tracks),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="sources", description="Show playback source readiness")
    async def sources(self, interaction: discord.Interaction) -> None:
        spotify = bool(self.settings.spotify_client_id and self.settings.spotify_client_secret)
        await interaction.response.send_message(
            embed=sources_embed(cookies=self.resolver.cookie_available, spotify=spotify),
            ephemeral=True,
        )

    async def close(self) -> None:
        await asyncio.gather(
            *(player.close() for player in self.players.values()),
            return_exceptions=True,
        )
        await self.resolver.close()
