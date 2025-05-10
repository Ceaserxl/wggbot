import platform
import json
import os
from dotenv import load_dotenv
from datetime import datetime


# Load Keys
load_dotenv()
LIVE_DISCORD_TOKEN = os.getenv('LIVE_DISCORD_TOKEN')
BETA_DISCORD_TOKEN = os.getenv('BETA_DISCORD_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
PLEX_URL = os.getenv('PLEX_URL')
PLEX_TOKEN = os.getenv('PLEX_TOKEN')
APP_URL = os.getenv('APP_URL')
SD_API_URL = os.getenv('SD_API_URL')


CHATGPT_MODEL = "gpt-4.1-nano"

if platform.system() == 'Windows':
    DISCORD_TOKEN = BETA_DISCORD_TOKEN
    SD_API_URL      = "http://127.0.0.1:7860"
else:
    DISCORD_TOKEN = LIVE_DISCORD_TOKEN

CHEAP = True

if CHEAP == True:
    DALLE_MODEL = 'dall-e-3'
    DALLE_QUALITY = 'standard'
else:
    DALLE_MODEL = 'gpt-image-1'
    DALLE_QUALITY = 'medium'

DALLE_RESOLUTION = '1024x1024'

# Load help message
def load_help_message():
    with open(os.path.join(os.path.dirname(__file__), 'jsons/help.json'), 'r') as file:
        return json.load(file)

def format_help_message(help_message):
    help_content = help_message["content"]
    embed_data = help_message["embeds"][0]

    help_content += f"\n\n{embed_data['title']}\n\n{embed_data['description']}\n\n"

    for field in embed_data["fields"]:
        help_content += f"**{field['name']}**\n{field['value']}\n\n"

    if "footer" in embed_data:
        help_content += f"{embed_data['footer']['text']}"

    return help_content

HELP_MESSAGE = load_help_message()
formatted_help_message = format_help_message(HELP_MESSAGE)

SYSTEM_MESSAGE = {
    "role": "system",
    "content": (
        "You are WheresGangBot, a custom bot powered by ChatGPT"
        "You can chat with users, play music in voice channels, and generate images based on prompts. "
        "Answer questions helpfully and provide commands for playing music and disconnecting. "
        "Keep your responses short and sweet and to the point, no instructions! "
        "Remember to keep all long messages shorter than two paragraphs!!"
        "You remember DM messages and can have continual conversations.\n\n"
        + formatted_help_message
    ),
    "timestamp": datetime.utcnow().isoformat()
}
