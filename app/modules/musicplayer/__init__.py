# modules/musicplayer/__init__.py

import os
import configparser
from datetime import datetime

SETTINGS_PATH = "settings.ini"
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "module_musicplayer.log")

# Default settings for the music player module
DEFAULTS = {
    "enabled": "true",
    "volume": "50",            # default playback volume %
    "autojoin": "true",       # whether bot auto-joins voice channels
    "max_queue": "25"          # max songs allowed in queue
}

# -----------------------------------------------------
# Logging
# -----------------------------------------------------
def log(msg: str):
    """Append musicplayer module logs."""
    os.makedirs(LOG_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


# -----------------------------------------------------
# Ensure settings.ini has required defaults
# -----------------------------------------------------
def ensure_settings():
    config = configparser.ConfigParser()

    if not os.path.exists(SETTINGS_PATH):
        log("settings.ini not found — cannot init musicplayer module.")
        return None

    config.read(SETTINGS_PATH)

    if "musicplayer" not in config:
        config["musicplayer"] = {}
        log("Created missing [musicplayer] section.")

    updated = False
    for key, value in DEFAULTS.items():
        if key not in config["musicplayer"]:
            config["musicplayer"][key] = value
            updated = True
            log(f"Inserted default key: {key}={value}")

    if updated:
        with open(SETTINGS_PATH, "w") as f:
            config.write(f)
        log("Saved updated musicplayer defaults to settings.ini.")

    return config


# -----------------------------------------------------
# init(bot) — executed by module_loader BEFORE registering commands
# -----------------------------------------------------
def init(bot):
    log("Initializing MusicPlayer module...")
    ensure_settings()
    log("Initialization complete.")
