from __future__ import annotations

from contextlib import suppress
from typing import Any, Protocol

import discord

from .player import GuildPlayer
from .presentation import QUEUE_PAGE_SIZE, now_playing_embed, queue_embed, status_embed


class MusicUIController(Protocol):
    async def can_control(self, interaction: discord.Interaction) -> bool: ...

    async def send_queue(
        self,
        interaction: discord.Interaction,
        player: GuildPlayer,
        *,
        ephemeral: bool,
    ) -> None: ...


class ManagedView(discord.ui.View):
    def __init__(self, *, timeout: float = 900) -> None:
        super().__init__(timeout=timeout)
        self.message: discord.Message | None = None

    def attach(self, message: discord.Message) -> None:
        self.message = message

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        if self.message is not None:
            with suppress(discord.HTTPException):
                await self.message.edit(view=self)


class PlaybackControls(ManagedView):
    def __init__(self, controller: MusicUIController, player: GuildPlayer) -> None:
        super().__init__()
        self.controller = controller
        self.player = player

    @discord.ui.button(
        label="Pause / Resume",
        emoji="⏯️",
        style=discord.ButtonStyle.secondary,
        custom_id="music:pause_resume",
    )
    async def pause_resume(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[Any],
    ) -> None:
        del button
        if not await self.controller.can_control(interaction):
            return
        changed = (
            self.player.resume() if self.player.playback_state == "paused" else self.player.pause()
        )
        if not changed:
            await interaction.response.send_message(
                embed=status_embed("Nothing playing", "There is no active track to control."),
                ephemeral=True,
            )
            return
        await interaction.response.edit_message(embed=now_playing_embed(self.player), view=self)

    @discord.ui.button(
        label="Skip",
        emoji="⏭️",
        style=discord.ButtonStyle.primary,
        custom_id="music:skip",
    )
    async def skip(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[Any],
    ) -> None:
        del button
        if not await self.controller.can_control(interaction):
            return
        track = self.player.current
        if not self.player.skip() or track is None:
            await interaction.response.send_message(
                embed=status_embed("Nothing to skip", "There is no active track."),
                ephemeral=True,
            )
            return
        await interaction.response.edit_message(
            embed=status_embed("Track skipped", f"Skipped **{track.label}**.", success=True),
            view=None,
        )
        self.stop()

    @discord.ui.button(
        label="Queue",
        emoji="📋",
        style=discord.ButtonStyle.secondary,
        custom_id="music:open_queue",
    )
    async def queue(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[Any],
    ) -> None:
        del button
        await self.controller.send_queue(interaction, self.player, ephemeral=True)

    @discord.ui.button(
        label="Stop",
        emoji="⏹️",
        style=discord.ButtonStyle.danger,
        custom_id="music:stop",
    )
    async def stop_playback(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[Any],
    ) -> None:
        del button
        if not await self.controller.can_control(interaction):
            return
        removed = self.player.clear()
        stopped = self.player.skip()
        if not stopped:
            await interaction.response.send_message(
                embed=status_embed("Nothing to stop", "There is no active track."),
                ephemeral=True,
            )
            return
        await interaction.response.edit_message(
            embed=status_embed(
                "Playback stopped",
                f"Stopped the player and removed **{removed}** queued tracks.",
                success=True,
            ),
            view=None,
        )
        self.stop()


class QueueControls(ManagedView):
    def __init__(
        self,
        controller: MusicUIController,
        player: GuildPlayer,
        page: int = 0,
    ) -> None:
        super().__init__()
        self.controller = controller
        self.player = player
        self.page = page
        self._sync_navigation()

    def _button(self, custom_id: str) -> discord.ui.Button[Any]:
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.custom_id == custom_id:
                return item
        raise RuntimeError(f"Missing queue button {custom_id}")

    def _sync_navigation(self) -> None:
        _, self.page, pages = queue_embed(self.player, self.page, QUEUE_PAGE_SIZE)
        self._button("queue:first").disabled = self.page == 0
        self._button("queue:previous").disabled = self.page == 0
        self._button("queue:page").label = f"{self.page + 1} / {pages}"
        self._button("queue:next").disabled = self.page >= pages - 1
        self._button("queue:last").disabled = self.page >= pages - 1

    async def _edit(self, interaction: discord.Interaction) -> None:
        embed, self.page, _ = queue_embed(self.player, self.page, QUEUE_PAGE_SIZE)
        self._sync_navigation()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.secondary, custom_id="queue:first")
    async def first(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        del button
        self.page = 0
        await self._edit(interaction)

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary, custom_id="queue:previous")
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        del button
        self.page -= 1
        await self._edit(interaction)

    @discord.ui.button(
        label="1 / 1",
        style=discord.ButtonStyle.secondary,
        disabled=True,
        custom_id="queue:page",
    )
    async def page_indicator(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        del interaction, button

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary, custom_id="queue:next")
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        del button
        self.page += 1
        await self._edit(interaction)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id="queue:last")
    async def last(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        del button
        _, _, pages = queue_embed(self.player, self.page, QUEUE_PAGE_SIZE)
        self.page = pages - 1
        await self._edit(interaction)

    @discord.ui.button(
        label="Skip",
        emoji="⏭️",
        style=discord.ButtonStyle.primary,
        row=1,
        custom_id="queue:skip",
    )
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        del button
        if not await self.controller.can_control(interaction):
            return
        track = self.player.current
        if not self.player.skip() or track is None:
            await interaction.response.send_message(
                embed=status_embed("Nothing to skip", "There is no active track."),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=status_embed("Track skipped", f"Skipped **{track.label}**.", success=True),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Shuffle",
        emoji="🔀",
        style=discord.ButtonStyle.secondary,
        row=1,
        custom_id="queue:shuffle",
    )
    async def shuffle(
        self, interaction: discord.Interaction, button: discord.ui.Button[Any]
    ) -> None:
        del button
        if not await self.controller.can_control(interaction):
            return
        self.player.shuffle()
        await self._edit(interaction)

    @discord.ui.button(
        label="Clear",
        emoji="🗑️",
        style=discord.ButtonStyle.danger,
        row=1,
        custom_id="queue:clear",
    )
    async def clear(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        del button
        if not await self.controller.can_control(interaction):
            return
        self.player.clear()
        self.page = 0
        await self._edit(interaction)
