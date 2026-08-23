from __future__ import annotations

import pytest

from wggbot.app import WGGBot


@pytest.mark.asyncio
async def test_only_music_application_commands_are_registered(settings_factory) -> None:
    bot = WGGBot(settings_factory())
    await bot.add_cog(bot.music)
    assert {command.name for command in bot.tree.get_commands()} == {"music"}
    music = next(command for command in bot.tree.get_commands() if command.name == "music")
    child_names = {command.name for command in music.commands}
    assert {"play", "now", "queue", "skip", "stop", "sources"} <= child_names
    await bot.close()


@pytest.mark.asyncio
async def test_health_snapshot_reports_music_without_module_state(settings_factory) -> None:
    bot = WGGBot(settings_factory())
    status, payload = bot.health_snapshot()
    assert status == 503
    assert payload == {
        "status": "starting",
        "discord": "disconnected",
        "music": "ready",
    }
    await bot.close()
