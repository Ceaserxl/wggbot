#!/usr/bin/env python3
"""One-time migration from legacy settings.ini to the ignored .env file."""

from __future__ import annotations

import configparser
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "settings.ini"
ENV = ROOT / ".env"

MAPPINGS = {
    ("wggbot", "debug"): "WGGBOT_DEBUG",
    ("wggbot", "live_discord_token"): "LIVE_DISCORD_TOKEN",
    ("wggbot", "beta_discord_token"): "BETA_DISCORD_TOKEN",
    ("musicplayer", "max_queue"): "MUSIC_MAX_QUEUE",
    ("musicplayer", "volume"): "MUSIC_DEFAULT_VOLUME",
}


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value
    return values


def main() -> None:
    if not LEGACY.exists():
        raise SystemExit("settings.ini does not exist; nothing to migrate")
    config = configparser.ConfigParser()
    config.read(LEGACY)
    values = parse_env(ENV)
    migrated: list[tuple[str, str]] = []
    for (section, option), env_key in MAPPINGS.items():
        if config.has_option(section, option):
            current = config.get(section, option).strip()
            if current and (env_key not in values or not values[env_key]):
                values[env_key] = current
            config.remove_option(section, option)
            migrated.append((section, option))

    defaults = {
        "WGGBOT_DEBUG": "false",
        "HEALTH_HOST": "0.0.0.0",
        "HEALTH_PORT": "8080",
        "SYNC_COMMANDS": "true",
        "LOG_LEVEL": "INFO",
        "YTDLP_COOKIE_FILE": "/app/cookies.txt",
        "MUSIC_MAX_QUEUE": "100",
        "MUSIC_MAX_PLAYLIST": "50",
        "MUSIC_IDLE_TIMEOUT": "300",
    }
    for key, value in defaults.items():
        values.setdefault(key, value)

    temporary = ENV.with_suffix(".tmp")
    temporary.write_text(
        "".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8"
    )
    os.chmod(temporary, 0o600)
    temporary.replace(ENV)
    os.chmod(ENV, 0o600)

    legacy_temporary = LEGACY.with_suffix(".tmp")
    with legacy_temporary.open("w", encoding="utf-8") as handle:
        config.write(handle)
    legacy_temporary.replace(LEGACY)
    print(f"Migrated {len(migrated)} legacy settings into .env; token values were not printed.")


if __name__ == "__main__":
    main()
