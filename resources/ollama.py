# ── Imports ─────────────────────────────────────────────────────────────
import aiohttp
import asyncio
import discord
import uuid
from resources import keys

# ── Constants ───────────────────────────────────────────────────────────
SYSTEM_CONTEXT = (
    "You are a helpful and friendly Discord assistant. Speak in a warm, conversational tone, "
    "as if you’re talking to a colleague—use natural language, empathy, and occasional informal touches. "
    "Provide clear, concise answers and structure them with headings or bullet points when helpful, "
    "but keep the overall feeling human and approachable. Stay under Discord’s 2000-character limit, "
    "and if trimming is needed, summarize gracefully."
)

# ── State ────────────────────────────────────────────────────────────────
# Tracks which threads have already received the system context
_initialized_threads = set()

# ── Ollama Query ─────────────────────────────────────────────────────────
async def query_ollama(prompt: str, model: str = keys.OLLAMA_MODEL) -> str:
    """
    Sends the given prompt (already including any needed context) to Ollama.
    """
    try:
        async with aiohttp.ClientSession() as session:
            # Health check
            try:
                async with session.get(
                    f"http://{keys.OLLAMA_IP}:11434/api/tags", timeout=3
                ) as health_resp:
                    if health_resp.status != 200:
                        return "❌ Ollama server is offline."
            except (asyncio.TimeoutError, Exception):
                return "❌ Ollama server is offline."

            # Generate response
            async with session.post(
                f"http://{keys.OLLAMA_IP}:11434/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("response", "❌ No response from Ollama.")
                else:
                    return "❌ Ollama API error"
    except Exception:
        return "❌ Ollama server is offline."

# ── Thread Context Helper ────────────────────────────────────────────────
async def get_thread_context(channel: discord.abc.Messageable, limit: int = 100) -> str:
    """
    Fetch up to `limit` most recent messages (newest→oldest) in this channel/thread,
    and format them as:
        User: <content>
        Bot: <content>
    """
    lines = []
    async for msg in channel.history(limit=limit, oldest_first=True):
        role = "Bot" if msg.author.bot else "User"
        lines.append(f"{role}: {msg.content}")
    return "\n".join(lines)

# ── Full Response Handler ───────────────────────────────────────────────
async def handle_ollama_response(message: discord.Message):
    # 1. Determine or create the thread
    if isinstance(message.channel, discord.Thread):
        thread = message.channel
    else:
        # Derive a unique title: slugify first line + short UUID
        raw_title = message.content.splitlines()[0]
        # Keep only alphanumeric and spaces, lowercase
        slug = ''.join(c if c.isalnum() or c.isspace() else ' ' for c in raw_title)
        slug = '-'.join(slug.lower().split())[:50]
        suffix = uuid.uuid4().hex[:8]
        title = f"{slug}-{suffix}" if slug else suffix

        thread = await message.create_thread(
            name=title,
            auto_archive_duration=60
        )

    # 2. Build the conversation prompt with up to 100 messages
    history = await get_thread_context(thread, limit=100)

    # 3. Prepare prompt, include system context only once
    if thread.id not in _initialized_threads:
        full_prompt = f"{SYSTEM_CONTEXT}\n\n{history}\nUser: {message.content}\nBot:"
        _initialized_threads.add(thread.id)
    else:
        full_prompt = f"{history}\nUser: {message.content}\nBot:"

    # 4. Send typing indicator, query Ollama, and post reply
    async with thread.typing():
        response = await query_ollama(full_prompt)
        await thread.send(response[:2000])
