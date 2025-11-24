# modules/ollama/__init__.py

import os
import configparser
from datetime import datetime

SETTINGS_PATH = "settings.ini"
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "module_ollama.log")

# Default values to inject if missing
DEFAULTS = {
    "ollama_host": "http://localhost:11434",
    "ollama_model": "llama3.1",
    "enabled": "true"
}


# -----------------------------------------------------
# Logging
# -----------------------------------------------------
def log(msg: str):
    os.makedirs(LOG_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


# -----------------------------------------------------
# Ensure settings.ini has ollama defaults
# -----------------------------------------------------
def ensure_settings():
    config = configparser.ConfigParser()

    if not os.path.exists(SETTINGS_PATH):
        log("settings.ini not found — skipping Ollama initialization.")
        return None

    config.read(SETTINGS_PATH)

    # Ensure section exists
    if "ollama" not in config:
        config["ollama"] = {}
        log("Added missing [ollama] section.")

    # Insert defaults when missing
    updated = False
    for key, value in DEFAULTS.items():
        if key not in config["ollama"]:
            config["ollama"][key] = value
            updated = True
            log(f"Inserted default key: {key}={value}")

    # Save changes
    if updated:
        with open(SETTINGS_PATH, "w") as f:
            config.write(f)
        log("Saved updated ollama settings to settings.ini.")

    return config


# -----------------------------------------------------
# init(bot) — called by module_loader
# -----------------------------------------------------
def init(bot):
    log("Initializing Ollama module...")
    ensure_settings()
    log("Ollama module initialization complete.")
