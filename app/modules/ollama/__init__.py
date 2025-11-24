# modules/ollama/__init__.py
import configparser
import os
import requests
from datetime import datetime

SETTINGS_PATH = "settings.ini"
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "module_ollama.log")

REQUIRED_SETTINGS = {
    "ollama_host": "http://localhost:11434",
    "ollama_model": "llama3.1",
    "enabled": "false"
}

# -------------------------------------------------
# Logging
# -------------------------------------------------
def log(msg):
    os.makedirs(LOG_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")

# -------------------------------------------------
# Ensure settings exist
# -------------------------------------------------
def ensure_settings():
    if not os.path.exists(SETTINGS_PATH):
        log("settings.ini not found — skipping auto-config.")
        return None

    config = configparser.ConfigParser()
    config.read(SETTINGS_PATH)

    if "ollama" not in config:
        config["ollama"] = {}
        log("Added missing [ollama] section.")

    updated = False
    for key, default_value in REQUIRED_SETTINGS.items():
        if key not in config["ollama"]:
            config["ollama"][key] = default_value
            updated = True
            log(f"Added missing key: {key}={default_value}")

    if updated:
        with open(SETTINGS_PATH, "w") as f:
            config.write(f)
        log("Saved updated settings.ini.")

    return config

# -------------------------------------------------
# Ollama server test
# -------------------------------------------------
def test_server(config):
    if config is None:
        return

    host = config["ollama"]["ollama_host"]

    try:
        log(f"Testing Ollama server at {host}...")
        r = requests.get(f"{host}/api/tags", timeout=2)

        if r.status_code == 200:
            log("Ollama server is ONLINE.")
            config["ollama"]["enabled"] = "true"
        else:
            log(f"Ollama responded with HTTP {r.status_code}")
            config["ollama"]["enabled"] = "false"

    except Exception as e:
        log(f"Ollama test failed: {e}")
        config["ollama"]["enabled"] = "false"

    # Always save updated enabled state
    with open(SETTINGS_PATH, "w") as f:
        config.write(f)
    log("Updated enabled flag in settings.ini.")

# -------------------------------------------------
# Auto-run on module import
# -------------------------------------------------
config = ensure_settings()
test_server(config)
