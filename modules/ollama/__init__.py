# /app/modules/ollama/__init__.py

import requests
from core.logging import sublog
from core.config import ensure_settings, cfg
import configparser
import os


# Default settings for the Ollama module
DEFAULTS = {
    "ollama_host": "http://localhost:11434",
    "default_model": "llama3.1:latest",
    "available_models": ""          # populated dynamically on init
}


SETTINGS_PATH = "settings.ini"
host = ""
default_model = ""


def init(bot):
    global host, default_model
    # Ensure defaults exist
    ensure_settings("ollama", DEFAULTS)

    # Load host + enabled
    host = cfg("ollama", "ollama_host", "http://localhost:11434").rstrip("/")
    default_model = cfg("ollama", "default_model", "llama3.1:latest")
    # Ping server
    ping_url = f"{host}/api/tags"
    sublog(f"[ping] Contacting Ollama at {host} ...")

    try:
        r = requests.get(ping_url, timeout=3)

        if r.status_code != 200:
            sublog(f"[error] Ollama responded with HTTP {r.status_code}")
            return

        sublog("[success] Ollama server reachable.")

        # Parse available models
        data = r.json()
        models = [m.get("name", "").strip() for m in data.get("models", []) if m.get("name")]

        if not models:
            sublog("[warning] No models returned.")

        # -----------------------------------------------------
        # Store available models into settings.ini
        # -----------------------------------------------------
        if os.path.exists(SETTINGS_PATH):
            cfgfile = configparser.ConfigParser()
            cfgfile.read(SETTINGS_PATH)

            cfgfile["ollama"]["available_models"] = ",".join(models)

            with open(SETTINGS_PATH, "w") as f:
                cfgfile.write(f)

            sublog("[saved] Updated available_models in settings.ini")

    except Exception as e:
        sublog(f"[error] Ollama not reachable: {e}")
        return

