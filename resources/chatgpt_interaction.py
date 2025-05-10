import requests
import json
from datetime import datetime
import os
import asyncio
from aiohttp import ClientSession
import discord
from resources import keys
from resources.conversation import load_conversation_history, save_conversation_history

OPENAI_API_KEY = keys.OPENAI_API_KEY
SYSTEM_MESSAGE = keys.SYSTEM_MESSAGE
MAX_TOKENS = 150  # Adjust based on the model you are using

# Ensure the images directory exists
os.makedirs('images', exist_ok=True)

def trim_conversation_history(conversation_history, max_tokens=MAX_TOKENS):
    total_tokens = 0
    trimmed_history = []
    for message in reversed(conversation_history):
        message_tokens = len(message["content"].split())
        if total_tokens + message_tokens > max_tokens:
            break
        trimmed_history.insert(0, message)
        total_tokens += message_tokens
    return trimmed_history

async def handle_dm_message(message, conversation_history):
    user_id = str(message.author.id)
    prompt = message.content

    # Add the user's message to the conversation history with timestamp
    conversation_history[user_id].append({
        "role": "user",
        "content": prompt,
        "timestamp": datetime.utcnow().isoformat()
    })

    headers = {
        'Authorization': f'Bearer {OPENAI_API_KEY}',
        'Content-Type': 'application/json'
    }

    # Trim the conversation history to stay within token limit
    trimmed_history = trim_conversation_history(conversation_history[user_id])

    data = {
        'model': keys.CHATGPT_MODEL,
        'messages': trimmed_history
    }

    async with message.channel.typing():
        async with ClientSession() as session:
            async with session.post('https://api.openai.com/v1/chat/completions', headers=headers, json=data) as response:
                if response.status == 200:
                    response_data = await response.json()
                    if 'choices' in response_data and len(response_data['choices']) > 0:
                        reply = response_data['choices'][0]['message']['content'].strip()
                        await message.reply(reply)
                        # Add the bot's reply to the conversation history with timestamp
                        conversation_history[user_id].append({
                            "role": "assistant",
                            "content": reply,
                            "timestamp": datetime.utcnow().isoformat()
                        })
                        #await save_conversation_history(conversation_history)
                    else:
                        await message.reply('No valid response received from OpenAI.')
                elif response.status == 400:
                    error_data = await response.json()
                    error_message = error_data.get("error", {}).get("message", "No error message provided.")
                    await message.reply(f"Error 400: Bad Request. Message: {error_message}")
                else:
                    await message.reply(f'Error from OpenAI API: {response.status}')
                    print(f'Error: {response.status}, Response: {await response.text()}')

def create_help_embed(user_mention=None):
    help_message = keys.HELP_MESSAGE
    embed_data = help_message["embeds"][0]

    title = embed_data["title"]

    embed = discord.Embed(
        title=title,
        description=embed_data["description"],
        color=embed_data["color"]
    )

    for field in embed_data["fields"]:
        embed.add_field(name=field["name"], value=field["value"], inline=field["inline"])

    if "footer" in embed_data:
        embed.set_footer(text=embed_data["footer"]["text"])

    return embed

async def handle_help_command(interaction: discord.Interaction):
    embed = create_help_embed(user_mention=interaction.user.mention)
    await interaction.followup.send(embed=embed)

async def handle_chat_command(interaction: discord.Interaction, prompt: str, conversation_history, client):
    await handle_guild_chat(interaction, prompt, conversation_history, client)

async def handle_guild_chat(interaction: discord.Interaction, prompt: str, conversation_history, client):
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
        'max_tokens': 150
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

async def download_image(image_url: str, file_path: str):
    response = requests.get(image_url)
    if response.status_code == 200:
        with open(file_path, 'wb') as file:
            file.write(response.content)
    else:
        raise Exception(f"Failed to download image. Status code: {response.status_code}")

async def generate_and_send_image(interaction: discord.Interaction, prompt: str, conversation_history):
    headers = {
        'Authorization': f'Bearer {OPENAI_API_KEY}',
        'Content-Type': 'application/json'
    }

    data = {
        'model': keys.DALLE_MODEL,
        'prompt': prompt,
        'size': keys.DALLE_RESOLUTION,  # Resolution based on the OS
        'quality': keys.DALLE_QUALITY,
        'n': 1
    }

    user_id = str(interaction.user.id)

    # Log the user's image prompt
    conversation_history[user_id].append({
        "role": "user",
        "content": f"Image prompt: {prompt}",
        "timestamp": datetime.utcnow().isoformat()
    })

    async with ClientSession() as session:
        async with session.post('https://api.openai.com/v1/images/generations', headers=headers, json=data) as response:
            if response.status == 200:
                response_data = await response.json()
                if 'data' in response_data and len(response_data['data']) > 0:
                    image_url = response_data['data'][0]['url']

                    # Generate a unique filename for the image and save it in the images directory
                    file_path = os.path.join('images', f"temp_image_{user_id}_{datetime.utcnow().timestamp()}.png")
                    await download_image(image_url, file_path)

                    # Create an embed with the image and prompt
                    embed = discord.Embed(title="", description=f"```\n{prompt}\n```\nModel: {keys.DALLE_MODEL}\nSize: {keys.DALLE_RESOLUTION}\nQuality: {keys.DALLE_QUALITY}\n")
                    file = discord.File(file_path, filename="image.png")
                    embed.set_image(url="attachment://image.png")

                    await interaction.followup.send(content=None, embed=embed, file=file)

                    # Log the image URL in the conversation history
                    conversation_history[user_id].append({
                        "role": "assistant",
                        "content": image_url,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    #await save_conversation_history(conversation_history)

                    # Clean up the temporary file
                    #os.remove(file_path)
                else:
                    await interaction.followup.send(content='No valid image generated.')
            else:
                error_data = await response.json()
                error_message = error_data.get("error", {}).get("message", "No error message provided.")
                await interaction.followup.send(content=f'{error_message}\n```{prompt}```')
                print(f'Error: {response.status}, Message: {error_message}')
