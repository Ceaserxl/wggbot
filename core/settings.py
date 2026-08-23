from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Expected a boolean value, got {value!r}")


def _as_int(name: str, value: str | None, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= parsed <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return parsed


@dataclass(frozen=True, slots=True)
class Settings:
    discord_token: str
    debug: bool
    health_host: str
    health_port: int
    sync_commands: bool
    log_level: str
    data_dir: Path
    module_state_path: Path
    ollama_url: str
    ollama_model: str
    comfyui_url: str
    ytdlp_cookie_file: Path | None
    music_max_queue: int
    music_max_playlist: int
    music_idle_timeout: int
    music_default_volume: int
    spotify_client_id: str | None
    spotify_client_secret: str | None


def load_settings(env_file: Path | None = None) -> Settings:
    dotenv_path = env_file or PROJECT_ROOT / ".env"
    # Docker injects the root-owned .env before dropping to the application
    # user. Local development can still read the file directly when allowed.
    if dotenv_path.is_file() and os.access(dotenv_path, os.R_OK):
        load_dotenv(dotenv_path, override=False)
    debug = _as_bool(os.getenv("WGGBOT_DEBUG"), False)
    token_key = "BETA_DISCORD_TOKEN" if debug else "LIVE_DISCORD_TOKEN"
    token = os.getenv(token_key, "").strip()
    if not token or token == "0":
        raise RuntimeError(f"{token_key} is required and must not be a placeholder")

    data_dir = Path(os.getenv("WGGBOT_DATA_DIR", PROJECT_ROOT / "data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    cookie_value = os.getenv("YTDLP_COOKIE_FILE", str(PROJECT_ROOT / "cookies.txt")).strip()
    cookie_path = Path(cookie_value).resolve() if cookie_value else None

    settings = Settings(
        discord_token=token,
        debug=debug,
        health_host=os.getenv("HEALTH_HOST", "0.0.0.0"),
        health_port=_as_int("HEALTH_PORT", os.getenv("HEALTH_PORT"), 8080, 1, 65535),
        sync_commands=_as_bool(os.getenv("SYNC_COMMANDS"), True),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        data_dir=data_dir,
        module_state_path=data_dir / "modules.json",
        ollama_url=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.1:latest"),
        comfyui_url=os.getenv("COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/"),
        ytdlp_cookie_file=cookie_path,
        music_max_queue=_as_int("MUSIC_MAX_QUEUE", os.getenv("MUSIC_MAX_QUEUE"), 100, 1, 1000),
        music_max_playlist=_as_int(
            "MUSIC_MAX_PLAYLIST", os.getenv("MUSIC_MAX_PLAYLIST"), 50, 1, 200
        ),
        music_idle_timeout=_as_int(
            "MUSIC_IDLE_TIMEOUT", os.getenv("MUSIC_IDLE_TIMEOUT"), 300, 30, 3600
        ),
        music_default_volume=_as_int(
            "MUSIC_DEFAULT_VOLUME", os.getenv("MUSIC_DEFAULT_VOLUME"), 50, 0, 200
        ),
        spotify_client_id=os.getenv("SPOTIFY_CLIENT_ID") or None,
        spotify_client_secret=os.getenv("SPOTIFY_CLIENT_SECRET") or None,
    )
    if settings.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL")
    return settings
