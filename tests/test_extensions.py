from __future__ import annotations

import pytest

from bot import WGGBot
from core.module_manager import ModulesCog


@pytest.mark.asyncio
async def test_default_extensions_load_reload_and_unload(settings_factory) -> None:
    bot = WGGBot(settings_factory())
    await bot.add_cog(ModulesCog(bot, bot.module_manager))
    await bot.module_manager.load_enabled()
    assert bot.module_manager.status_snapshot() == {
        "musicplayer": "loaded",
        "ollama": "loaded",
        "stablediffusion": "disabled",
    }
    assert {command.name for command in bot.tree.get_commands()} == {
        "modules",
        "music",
        "ollama",
    }

    await bot.module_manager.reload("musicplayer")
    await bot.module_manager.enable("stablediffusion")
    assert "modules.stablediffusion" in bot.extensions
    assert "imagine" in {command.name for command in bot.tree.get_commands()}

    await bot.module_manager.disable("stablediffusion")
    assert "imagine" not in {command.name for command in bot.tree.get_commands()}
    await bot.module_manager.shutdown()
    await bot.close()


@pytest.mark.asyncio
async def test_module_commands_require_owner(settings_factory) -> None:
    bot = WGGBot(settings_factory())
    cog = ModulesCog(bot, bot.module_manager)

    class FakeResponse:
        def __init__(self) -> None:
            self.message = ""

        async def send_message(self, message: str, **kwargs: object) -> None:
            self.message = message

    class FakeInteraction:
        user = object()
        response = FakeResponse()

    async def not_owner(user: object) -> bool:
        return False

    bot.is_owner = not_owner
    interaction = FakeInteraction()
    assert await cog.interaction_check(interaction) is False
    assert "Only the bot owner" in interaction.response.message
    await bot.close()
