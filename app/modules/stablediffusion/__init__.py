# modules/stablediffusion/__init__.py

import os
import configparser
from datetime import datetime

SETTINGS_PATH = "settings.ini"
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "module_stablediffusion.log")

# ComfyUI-specific defaults
DEFAULTS = {
    "sd_host": "http://127.0.0.1:8188",   # ComfyUI API
    # Qwen workflow defaults (fixed)
    "default_width": "512",
    "default_height": "512",
    "default_steps": "4",
    "default_seed": "0",
}


# -----------------------------------------------------
# Logging helper
# -----------------------------------------------------
def log(msg: str):
    os.makedirs(LOG_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


# -----------------------------------------------------
# Ensure [stablediffusion] section exists with defaults
# -----------------------------------------------------
def ensure_settings():
    config = configparser.ConfigParser()

    if not os.path.exists(SETTINGS_PATH):
        log("⚠ settings.ini not found — stablediffusion module cannot initialize.")
        return None

    config.read(SETTINGS_PATH)

    if "stablediffusion" not in config:
        config["stablediffusion"] = {}
        log("Created missing [stablediffusion] section.")

    section = config["stablediffusion"]
    updated = False

    # Insert defaults only if missing
    for key, value in DEFAULTS.items():
        if key not in section:
            section[key] = value
            updated = True
            log(f"Inserted default setting: {key}={value}")

    if updated:
        with open(SETTINGS_PATH, "w") as f:
            config.write(f)
        log("Updated stablediffusion settings.ini with defaults.")

    return config


# -----------------------------------------------------
# init(bot) — runs before command registration
# -----------------------------------------------------
def init(bot):
    log("Initializing Stable Diffusion module (ComfyUI backend)...")
    ensure_settings()
    log("Stable Diffusion module ready.")
