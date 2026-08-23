from __future__ import annotations

import asyncio

import discord
import pytest

from wggbot.music.models import Track
from wggbot.music.player import GuildPlayer
from wggbot.music.presentation import QUEUE_PAGE_SIZE, now_playing_embed, queue_embed, queued_embed
from wggbot.music.ui import PlaybackControls, QueueControls


class FakeResolver:
    async def stream_url(self, track: Track) -> str:
        return track.webpage_url


class FakeController:
    async def can_control(self, interaction: discord.Interaction) -> bool:
        del interaction
        return True

    async def send_queue(
        self,
        interaction: discord.Interaction,
        player: GuildPlayer,
        *,
        ephemeral: bool,
    ) -> None:
        del interaction, player, ephemeral


class FakeResponse:
    def __init__(self) -> None:
        self.sent: dict[str, object] | None = None
        self.edited: dict[str, object] | None = None

    async def send_message(self, content: str | None = None, **kwargs: object) -> None:
        self.sent = {"content": content, **kwargs}

    async def edit_message(self, **kwargs: object) -> None:
        self.edited = kwargs


class FakeInteraction:
    def __init__(self) -> None:
        self.response = FakeResponse()


class FakeVoiceClient:
    def __init__(self) -> None:
        self.playing = True
        self.paused = False
        self.stopped = False
        self.source = None

    def is_playing(self) -> bool:
        return self.playing

    def is_paused(self) -> bool:
        return self.paused

    def is_connected(self) -> bool:
        return False

    def stop(self) -> None:
        self.playing = False
        self.stopped = True


def make_track(number: int) -> Track:
    return Track(
        title=f"Track {number}",
        artist=f"Artist {number}",
        webpage_url=f"https://example.com/{number}",
        requester_id=number,
        requester_mention=f"<@{number}>",
        duration=180 + number,
        source="Youtube",
        thumbnail="https://example.com/cover.jpg",
    )


@pytest.mark.asyncio
async def test_queue_embed_has_numbered_pages_and_track_details(settings_factory) -> None:
    player = GuildPlayer(1, FakeResolver(), settings_factory(music_max_queue=30))
    player._worker.cancel()
    await asyncio.gather(player._worker, return_exceptions=True)
    player.current = make_track(99)
    player.enqueue([make_track(number) for number in range(1, 19)])

    embed, page, pages = queue_embed(player, page=1)
    assert page == 1
    assert pages == 3
    assert embed.title == "Music queue"
    assert "`09`" in (embed.description or "")
    assert "Track 9" in (embed.description or "")
    assert "Track 16" in (embed.description or "")
    assert "Track 17" not in (embed.description or "")
    assert embed.fields[2].value == "`2 / 3`"
    await player.close()


@pytest.mark.asyncio
async def test_queue_controls_expose_paging_and_direct_actions(settings_factory) -> None:
    player = GuildPlayer(1, FakeResolver(), settings_factory(music_max_queue=30))
    player._worker.cancel()
    await asyncio.gather(player._worker, return_exceptions=True)
    player.enqueue([make_track(number) for number in range(1, QUEUE_PAGE_SIZE + 2)])
    view = QueueControls(FakeController(), player)
    buttons = {
        item.custom_id: item for item in view.children if isinstance(item, discord.ui.Button)
    }
    assert set(buttons) == {
        "queue:first",
        "queue:previous",
        "queue:page",
        "queue:next",
        "queue:last",
        "queue:skip",
        "queue:shuffle",
        "queue:clear",
    }
    assert buttons["queue:first"].disabled
    assert buttons["queue:previous"].disabled
    assert not buttons["queue:next"].disabled
    assert buttons["queue:page"].label == "1 / 2"
    await player.close()


@pytest.mark.asyncio
async def test_now_playing_and_queued_cards_have_controls_and_metadata(settings_factory) -> None:
    player = GuildPlayer(1, FakeResolver(), settings_factory())
    player._worker.cancel()
    await asyncio.gather(player._worker, return_exceptions=True)
    player.current = make_track(1)
    player.enqueue([make_track(2)])

    now = now_playing_embed(player)
    queued = queued_embed([make_track(2)], len(player.queue))
    controls = PlaybackControls(FakeController(), player)
    labels = {item.label for item in controls.children if isinstance(item, discord.ui.Button)}
    assert now.author.name == "WGGBot Music  •  Now playing"
    assert len(now.fields) == 6
    assert queued.author.name == "WGGBot Music  •  Added to queue"
    assert {"Pause / Resume", "Skip", "Queue", "Stop"} == labels
    await player.close()


@pytest.mark.asyncio
async def test_skip_button_stops_current_track_and_replaces_stale_controls(
    settings_factory,
) -> None:
    player = GuildPlayer(1, FakeResolver(), settings_factory())
    player._worker.cancel()
    await asyncio.gather(player._worker, return_exceptions=True)
    player.current = make_track(1)
    voice = FakeVoiceClient()
    player.voice_client = voice
    view = PlaybackControls(FakeController(), player)
    skip = next(
        item
        for item in view.children
        if isinstance(item, discord.ui.Button) and item.custom_id == "music:skip"
    )
    interaction = FakeInteraction()

    await skip.callback(interaction)

    assert voice.stopped
    assert interaction.response.edited is not None
    edited_embed = interaction.response.edited["embed"]
    assert isinstance(edited_embed, discord.Embed)
    assert edited_embed.title == "Track skipped"
    assert interaction.response.edited["view"] is None
    await player.close()


@pytest.mark.asyncio
async def test_queue_buttons_move_pages_and_clear_live_queue(settings_factory) -> None:
    player = GuildPlayer(1, FakeResolver(), settings_factory(music_max_queue=30))
    player._worker.cancel()
    await asyncio.gather(player._worker, return_exceptions=True)
    player.enqueue([make_track(number) for number in range(1, QUEUE_PAGE_SIZE + 2)])
    view = QueueControls(FakeController(), player)
    buttons = {
        item.custom_id: item for item in view.children if isinstance(item, discord.ui.Button)
    }

    next_interaction = FakeInteraction()
    await buttons["queue:next"].callback(next_interaction)
    assert view.page == 1
    assert next_interaction.response.edited is not None
    next_embed = next_interaction.response.edited["embed"]
    assert isinstance(next_embed, discord.Embed)
    assert next_embed.fields[2].value == "`2 / 2`"

    clear_interaction = FakeInteraction()
    await buttons["queue:clear"].callback(clear_interaction)
    assert not player.queue
    assert view.page == 0
    assert clear_interaction.response.edited is not None
    clear_embed = clear_interaction.response.edited["embed"]
    assert isinstance(clear_embed, discord.Embed)
    assert "No upcoming tracks" in (clear_embed.description or "")
    await player.close()
