from __future__ import annotations

import asyncio

import pytest

from modules.musicplayer.models import Track
from modules.musicplayer.player import GuildPlayer, QueueFullError


class FakeResolver:
    async def stream_url(self, track: Track) -> str:
        return track.webpage_url


def make_track(number: int) -> Track:
    return Track(
        title=f"Track {number}",
        artist="Artist",
        webpage_url=f"https://example.com/{number}",
        requester_id=1,
        requester_mention="<@1>",
    )


@pytest.mark.asyncio
async def test_queue_mutations_are_bounded_and_ordered(settings_factory) -> None:
    player = GuildPlayer(1, FakeResolver(), settings_factory(music_max_queue=3))
    player._worker.cancel()
    await asyncio.gather(player._worker, return_exceptions=True)
    player.enqueue([make_track(1), make_track(2), make_track(3)])
    with pytest.raises(QueueFullError):
        player.enqueue([make_track(4)])
    moved = player.move(3, 1)
    assert moved.title == "Track 3"
    assert [track.title for track in player.queue] == ["Track 3", "Track 1", "Track 2"]
    removed = player.remove(2)
    assert removed.title == "Track 1"
    assert player.clear() == 2
    await player.close()


@pytest.mark.asyncio
async def test_one_worker_serializes_all_tracks(settings_factory) -> None:
    player = GuildPlayer(2, FakeResolver(), settings_factory())
    active = 0
    maximum_active = 0
    played: list[str] = []

    async def fake_play(track: Track) -> None:
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        played.append(track.title)
        await asyncio.sleep(0.01)
        active -= 1

    player._play = fake_play
    player.enqueue([make_track(1), make_track(2), make_track(3)])
    for _ in range(100):
        if len(played) == 3 and player.current is None:
            break
        await asyncio.sleep(0.01)
    assert played == ["Track 1", "Track 2", "Track 3"]
    assert maximum_active == 1
    await player.close()
