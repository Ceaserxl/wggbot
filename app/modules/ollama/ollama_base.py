# modules/ollama/ollama_base.py

import aiohttp
import configparser

SETTINGS_PATH = "settings.ini"


# ---------------------------------------------------------
# Load Ollama settings
# ---------------------------------------------------------
def load_settings():
    cfg = configparser.ConfigParser()
    cfg.read(SETTINGS_PATH)

    if "ollama" not in cfg:
        return None

    return {
        "host": cfg["ollama"].get("ollama_host", "http://localhost:11434").rstrip("/"),
        "model": cfg["ollama"].get("ollama_model", "llama3.1"),
        "enabled": cfg["ollama"].get("enabled", "false").lower() == "true"
    }


OLLAMA = load_settings()


# ---------------------------------------------------------
# ask_ollama(prompt)
# Core logic used by commands
# ---------------------------------------------------------
async def ask_ollama(prompt: str) -> str:
    """
    Sends a prompt to the Ollama server using settings.ini values.
    """

    if not OLLAMA:
        return "❌ Ollama settings missing."

    if not OLLAMA["enabled"]:
        return "❌ Ollama module is disabled in settings.ini."

    url = f"{OLLAMA['host']}/api/generate"

    async with aiohttp.ClientSession() as session:
        try:
            response = await session.post(
                url,
                json={
                    "model": OLLAMA["model"],
                    "prompt": prompt,
                    "stream": False
                },
                timeout=10
            )

            if response.status != 200:
                return f"❌ Ollama error (HTTP {response.status})"

            data = await response.json()
            return data.get("response", "").strip() or "(empty response)"

        except Exception as e:
            return f"❌ Ollama request failed: {e}"
