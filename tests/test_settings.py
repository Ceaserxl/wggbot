from __future__ import annotations

import logging
from pathlib import Path

import pytest

from core.logging import SecretRedactionFilter
from core.settings import load_settings


def test_load_settings_reads_token_without_exposing_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key in ("LIVE_DISCORD_TOKEN", "BETA_DISCORD_TOKEN", "WGGBOT_DEBUG"):
        monkeypatch.delenv(key, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "LIVE_DISCORD_TOKEN=live-secret\n"
        "BETA_DISCORD_TOKEN=beta-secret\n"
        "WGGBOT_DATA_DIR=" + str(tmp_path / "data") + "\n",
        encoding="utf-8",
    )
    settings = load_settings(env_file)
    assert settings.discord_token == "live-secret"
    assert settings.data_dir == (tmp_path / "data").resolve()


def test_load_settings_rejects_placeholder_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIVE_DISCORD_TOKEN", "0")
    monkeypatch.setenv("WGGBOT_DEBUG", "false")
    with pytest.raises(RuntimeError, match="LIVE_DISCORD_TOKEN"):
        load_settings(tmp_path / "missing.env")


def test_injected_environment_does_not_require_readable_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("LIVE_DISCORD_TOKEN=file-token\n", encoding="utf-8")
    monkeypatch.setenv("LIVE_DISCORD_TOKEN", "injected-token")
    monkeypatch.setenv("WGGBOT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr("core.settings.os.access", lambda path, mode: False)
    settings = load_settings(env_file)
    assert settings.discord_token == "injected-token"


def test_redaction_filter_masks_discord_token_shape() -> None:
    token = "A" * 24 + "." + "B" * 6 + "." + "C" * 30
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "token=%s", (token,), None)
    assert SecretRedactionFilter().filter(record)
    assert token not in record.getMessage()
    assert "REDACTED" in record.getMessage()
