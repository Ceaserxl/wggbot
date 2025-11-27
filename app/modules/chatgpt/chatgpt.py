# modules/chatgpt/chatgpt.py

# ── Imports ─────────────────────────────────────────────────────────────
import os
import requests
from datetime import datetime
from aiohttp import ClientSession
import discord
from resources import keys

# ── Constants and Config ────────────────────────────────────────────────
OPENAI_API_KEY = keys.OPENAI_API_KEY
SYSTEM_MESSAGE = keys.SYSTEM_MESSAGE
MAX_TOKENS     = 150  # Adjust based on model
os.makedirs('images', exist_ok=True)

# ── DM Chat Handler ─────────────────────────────────────────────────────
async def handle_dm_message(message):
    prompt = message.content
    headers = {
        'Authorization': f'Bearer {OPENAI_API_KEY}',
        'Content-Type': 'application/json'
    }
    data = {
        'model': keys.CHATGPT_MODEL,
        'messages': [{'role': 'user', 'content': prompt}]
    }

    async with message.channel.typing():
        async with ClientSession() as session:
            async with session.post('https://api.openai.com/v1/chat/completions', headers=headers, json=data) as response:
                if response.status == 200:
                    response_data = await response.json()
                    if 'choices' in response_data and len(response_data['choices']) > 0:
                        reply = response_data['choices'][0]['message']['content'].strip()
                        await message.reply(reply)
                    else:
                        await message.reply('No valid response received from OpenAI.')
                elif response.status == 400:
                    error_data = await response.json()
                    error_message = error_data.get("error", {}).get("message", "No error message provided.")
                    await message.reply(f"Error 400: Bad Request. Message: {error_message}")
                else:
                    await message.reply(f'Error from OpenAI API: {response.status}')
                    print(f'Error: {response.status}, Response: {await response.text()}')

# ── Slash Command Chat Handler ──────────────────────────────────────────
async def handle_chat_command(interaction: discord.Interaction, prompt: str, client):
    await handle_guild_chat(interaction, prompt, client)

# ── Guild Chat Handler with History ─────────────────────────────────────
async def handle_guild_chat(interaction: discord.Interaction, prompt: str, client):
    async for msg in interaction.channel.history(limit=100):
        if msg.author == client.user:
            last_bot_message = msg.content
            break
    else:
        last_bot_message = SYSTEM_MESSAGE['content']

    headers = {
        'Authorization': f'Bearer {OPENAI_API_KEY}',
        'Content-Type': 'application/json'
    }
    data = {
        'model': keys.CHATGPT_MODEL,
        'messages': [
            SYSTEM_MESSAGE,
            {"role": "assistant", "content": last_bot_message},
            {"role": "user", "content": prompt}
        ],
        'max_tokens': MAX_TOKENS
    }

    async with ClientSession() as session:
        async with session.post('https://api.openai.com/v1/chat/completions', headers=headers, json=data) as response:
            if response.status == 200:
                response_data = await response.json()
                if 'choices' in response_data and len(response_data['choices']) > 0:
                    reply = response_data['choices'][0]['message']['content'].strip()
                    await interaction.followup.send(reply)
            elif response.status == 400:
                error_data = await response.json()
                error_message = error_data.get("error", {}).get("message", "No error message provided.")
                await interaction.followup.send(f"Error 400: Bad Request. Message: {error_message}")
            else:
                await interaction.followup.send(f'Error from OpenAI API: {response.status}')
                print(f'Error: {response.status}, Response: {await response.text()}')

# ── Image Generation ────────────────────────────────────────────────────
async def download_image(image_url: str, file_path: str):
    response = requests.get(image_url)
    if response.status_code == 200:
        with open(file_path, 'wb') as file:
            file.write(response.content)
    else:
        raise Exception(f"Failed to download image. Status code: {response.status_code}")

async def generate_and_send_image(interaction: discord.Interaction, prompt: str):
    headers = {
        'Authorization': f'Bearer {OPENAI_API_KEY}',
        'Content-Type': 'application/json'
    }
    data = {
        'model': keys.DALLE_MODEL,
        'prompt': prompt,
        'size': keys.DALLE_RESOLUTION,
        'quality': keys.DALLE_QUALITY,
        'n': 1
    }

    user_id = str(interaction.user.id)

    async with ClientSession() as session:
        async with session.post('https://api.openai.com/v1/images/generations', headers=headers, json=data) as response:
            if response.status == 200:
                response_data = await response.json()
                if 'data' in response_data and len(response_data['data']) > 0:
                    image_url = response_data['data'][0]['url']
                    file_path = os.path.join('images', f"temp_image_{user_id}_{datetime.utcnow().timestamp()}.png")
                    await download_image(image_url, file_path)

                    embed = discord.Embed(
                        title="🎨 ChatGPT | Dall-E-3 🎨",
                        color=discord.Color.green(),
                        description="\n".join([
                            f"**Prompt:**\n```{prompt}```"
                        ]))
                    
                    file = discord.File(file_path, filename="image.png")
                    embed.set_image(url="attachment://image.png")
                    await interaction.followup.send(content=None, embed=embed, file=file)

                else:
                    await interaction.followup.send(content='No valid image generated.')
            else:
                error_data = await response.json()
                error_message = error_data.get("error", {}).get("message", "No error message provided.")
                await interaction.followup.send(content=f'{error_message}\n```{prompt}```')
                print(f'Error: {response.status}, Message: {error_message}')
