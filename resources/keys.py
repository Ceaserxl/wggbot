# resources/keys.py

# ── Imports ─────────────────────────────────────────────────────────────
import os
import platform
from datetime import datetime
from dotenv import load_dotenv

# ── Load Environment Variables ──────────────────────────────────────────
load_dotenv(override=True)

LIVE_DISCORD_TOKEN = os.getenv('LIVE_DISCORD_TOKEN')
BETA_DISCORD_TOKEN = os.getenv('BETA_DISCORD_TOKEN')
OPENAI_API_KEY     = os.getenv('OPENAI_API_KEY')
PLEX_URL           = os.getenv('PLEX_URL')
PLEX_TOKEN         = os.getenv('PLEX_TOKEN')
APP_URL            = os.getenv('APP_URL')
SD_API_URL         = os.getenv('SD_API_URL')
OLLAMA_IP          = os.getenv('OLLAMA_IP')
OLLAMA_CHANNEL_ID  = int(os.getenv('OLLAMA_CHANNEL_ID'))
OLLAMA_MODEL       = os.getenv('OLLAMA_MODEL')

# ── Platform-Specific Overrides ─────────────────────────────────────────
if platform.system() == 'Windows':
    DISCORD_TOKEN = BETA_DISCORD_TOKEN
    SD_API_URL    = "http://127.0.0.1:7860"
    OLLAMA_IP     = "localhost"
else:
    DISCORD_TOKEN = LIVE_DISCORD_TOKEN

# ── ChatGPT Model Configuration ────────────────────────────────────────
CHATGPT_MODEL = "gpt-4.1-nano"

# ── DALL·E Configuration ───────────────────────────────────────────────
CHEAP = True

if CHEAP:
    DALLE_MODEL   = 'dall-e-3'
    DALLE_QUALITY = 'standard'
else:
    DALLE_MODEL   = 'gpt-image-1'
    DALLE_QUALITY = 'medium'

DALLE_RESOLUTION = '1024x1024'

# ── Default System Message ─────────────────────────────────────────────
SYSTEM_MESSAGE = {
    "role": "system",
    "content": (
        "You are WheresGangBot, a custom bot powered by ChatGPT. "
        "You can chat with users, play music in voice channels, and generate images based on prompts. "
        "Answer questions helpfully and provide commands for playing music and disconnecting. "
        "Keep your responses short and sweet and to the point, no instructions!"
    ),
    "timestamp": datetime.utcnow().isoformat()
}
