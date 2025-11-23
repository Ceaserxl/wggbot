# resources/ollama.py
# ── Imports ─────────────────────────────────────────────────────────────
import aiohttp
import asyncio
import discord
from resources import keys

# ── Constants ───────────────────────────────────────────────────────────
SYSTEM_CONTEXT = (
    "You are a helpful and friendly Discord assistant. Speak in a natural, conversational tone, "
    "like you're chatting with a colleague. Keep answers clear, brief, and approachable. Use headings or bullets if useful, "
    "but avoid sounding robotic. Always stay under 1500 characters—summarize when needed and skip filler. "
    "Never include labels like 'Bot:' or 'Assistant:' in your replies."
)
CHAT_LIMIT = 200

# ── State ────────────────────────────────────────────────────────────────
# Tracks which threads have already received the system context
_initialized_threads = set()

# ── Ollama Query ─────────────────────────────────────────────────────────
async def query_ollama(prompt: str, model: str = keys.OLLAMA_MODEL) -> str:
    print("Ollama request sent to IP Address: " + keys.OLLAMA_IP)
    # Sends the given prompt to Ollama, first performing a health check.
    async with aiohttp.ClientSession() as session:
        # Health check + error handling
        try:
            health_resp = await session.get(
                f"http://{keys.OLLAMA_IP}:11434/api/tags", timeout=3
            )
            if health_resp.status != 200:
                return "❌ Ollama server is offline."
        except (asyncio.TimeoutError, aiohttp.ClientError):
            return "❌ Ollama server is offline."

        # Generate response
        try:
            resp = await session.post(
                f"http://{keys.OLLAMA_IP}:11434/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                headers={"Content-Type": "application/json"}
            )
            if resp.status == 200:
                data = await resp.json()
                return data.get("response", "❌ No response from Ollama.")
            return "❌ Ollama API error"
        except (asyncio.TimeoutError, aiohttp.ClientError):
            return "❌ Ollama server is offline."

# ── Thread Context Helper ────────────────────────────────────────────────
async def get_thread_context(channel: discord.abc.Messageable, limit: int = CHAT_LIMIT) -> str:
    
    # Fetch up to `limit` most recent messages (oldest→newest) in this channel/thread,
    # and format them as:
    #     User: <content>
    #     Bot: <content>
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
        words = message.content.split()[:5]
        title = " ".join(words).strip()
        if len(title) > 90:
            title = title[:87].rstrip() + "..."
        thread = await message.create_thread(
            name=title or "conversation",
            auto_archive_duration=60
        )

    # 2. Build conversation prompt
    history = await get_thread_context(thread, limit=CHAT_LIMIT)

    # 3. Prepare prompt, include system context only once
    if thread.id not in _initialized_threads:
        full_prompt = f"{SYSTEM_CONTEXT}\n\n{history}\nUser: {message.content}\nBot:"
        _initialized_threads.add(thread.id)
    else:
        full_prompt = f"{history}\nUser: {message.content}\nBot:"

    # 4. Send typing indicator, query Ollama, and post reply
    async with thread.typing():
        response = await query_ollama(full_prompt)
        response = response[:2000]

        if isinstance(message.channel, discord.Thread):
            # For replies within an existing thread
            await message.reply(response, mention_author=False)
        else:
            # For the very first bot message in the new thread
            await thread.send(response)
