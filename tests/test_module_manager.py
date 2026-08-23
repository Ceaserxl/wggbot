from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.module_manager import MODULES, ModuleManager


class FakeBot:
    def __init__(self) -> None:
        self.extensions: dict[str, object] = {}
        self.calls: list[tuple[str, str]] = []

    async def load_extension(self, extension: str) -> None:
        self.calls.append(("load", extension))
        self.extensions[extension] = object()

    async def unload_extension(self, extension: str) -> None:
        self.calls.append(("unload", extension))
        self.extensions.pop(extension)

    async def reload_extension(self, extension: str) -> None:
        self.calls.append(("reload", extension))


@pytest.mark.asyncio
async def test_default_modules_load_but_stable_diffusion_stays_disabled(tmp_path: Path) -> None:
    bot = FakeBot()
    manager = ModuleManager(bot, tmp_path / "modules.json")
    await manager.load_enabled()
    assert manager.status_snapshot() == {
        "musicplayer": "loaded",
        "ollama": "loaded",
        "stablediffusion": "disabled",
    }


@pytest.mark.asyncio
async def test_enable_disable_reload_persist_state(tmp_path: Path) -> None:
    bot = FakeBot()
    state_path = tmp_path / "modules.json"
    manager = ModuleManager(bot, state_path)
    await manager.load_enabled()
    await manager.enable("stablediffusion")
    await manager.reload("stablediffusion")
    await manager.disable("ollama")
    state = json.loads(state_path.read_text(encoding="utf-8"))["enabled"]
    assert state["stablediffusion"] is True
    assert state["ollama"] is False
    assert ("reload", MODULES["stablediffusion"].extension) in bot.calls


def test_unknown_module_is_rejected(tmp_path: Path) -> None:
    manager = ModuleManager(FakeBot(), tmp_path / "modules.json")
    with pytest.raises(ValueError, match="Unknown module"):
        manager.definition("not-real")
