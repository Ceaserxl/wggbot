# /app/modules/ollama/ollama_base.py
import aiohttp
from core.logging import sublog
from . import host, default_model
# ---------------------------------------------------------
# Load Ollama settings (fresh every call)
# ---------------------------------------------------------
def load_settings():
    return {
        "host": host,
        "model": default_model,
    }

# ---------------------------------------------------------
# ask_ollama(prompt, model=None)
# ---------------------------------------------------------
async def ask_ollama(prompt: str, model: str = None) -> str:
    """
    Sends a prompt to the Ollama server.
    model=None → use default from settings.ini
    """
    OLLAMA = load_settings()

    # Resolve model
    chosen_model = model if model else OLLAMA["model"]
    url = f"{OLLAMA['host']}/api/generate"

    sublog(f"[ollama] [base] Request → model='{chosen_model}'")

    try:
        async with aiohttp.ClientSession() as session:
            response = await session.post(
                url,
                json={
                    "model": chosen_model,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=30
            )

            if response.status != 200:
                sublog(f"[ollama] [base] ERROR HTTP {response.status}", print_console=False)
                return f"❌ Ollama returned HTTP {response.status}"

            data = await response.json()
            reply = data.get("response", "").strip()

            if not reply:
                sublog("[ollama] [base] WARN empty response", print_console=False)
                return "(empty response)"

            sublog("[ollama] [base] SUCCESS response received", print_console=False)
            return reply

    except Exception as e:
        sublog(f"[ollama] [base] EXCEPTION {e}", print_console=False)
        return f"❌ Ollama request failed: {e}"
