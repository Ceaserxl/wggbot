# resources/ollama.py
# ── Imports ─────────────────────────────────────────────────────────────
import aiohttp
import asyncio
from resources import keys

# ── Constants ───────────────────────────────────────────────────────────
SYSTEM_CONTEXT = (
    "You are a helpful Discord bot. Format all responses using Discord-supported Markdown to enhance clarity. "
    "Use section headings, bullet points, numbered lists, and code blocks where appropriate. "
    "Organize answers with clear titles and sections when explaining complex topics. "
    "Keep the response under Discord's 2000-character limit. If the content is too long, summarize it intelligently "
    "and only mention the limit if trimming is required."
)

# ── Ollama Query Handler ────────────────────────────────────────────────
async def query_ollama(prompt: str, model: str = "artifish/llama3.2-uncensored:latest") -> str:
    try:
        full_prompt = f"{SYSTEM_CONTEXT}\n\nUser: {prompt}"
        async with aiohttp.ClientSession() as session:
            # Health check
            try:
                async with session.get(f"http://{keys.OLLAMA_IP}:11434/api/tags", timeout=3) as health_resp:
                    if health_resp.status != 200:
                        return "❌ Ollama server is offline."
            except (asyncio.TimeoutError, Exception):
                return "❌ Ollama server is offline."

            # Generate response
            async with session.post(
                f"http://{keys.OLLAMA_IP}:11434/api/generate",
                json={"model": model, "prompt": full_prompt, "stream": False},
                headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("response", "❌ No response from Ollama.")
                else:
                    return "❌ Ollama API error"
    except Exception:
        return "❌ Ollama server is offline."
