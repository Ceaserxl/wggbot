from __future__ import annotations

from pathlib import Path

import pytest

from core.settings import Settings


@pytest.fixture
def settings_factory(tmp_path: Path):
    def factory(**overrides: object) -> Settings:
        values: dict[str, object] = {
            "discord_token": "test-token-not-real",
            "debug": False,
            "health_host": "127.0.0.1",
            "health_port": 8080,
            "sync_commands": False,
            "log_level": "INFO",
            "data_dir": tmp_path,
            "module_state_path": tmp_path / "modules.json",
            "ollama_url": "http://127.0.0.1:11434",
            "ollama_model": "test-model",
            "comfyui_url": "http://127.0.0.1:8188",
            "ytdlp_cookie_file": tmp_path / "cookies.txt",
            "music_max_queue": 5,
            "music_max_playlist": 4,
            "music_idle_timeout": 30,
            "music_default_volume": 50,
            "spotify_client_id": None,
            "spotify_client_secret": None,
        }
        values.update(overrides)
        return Settings(**values)

    return factory
