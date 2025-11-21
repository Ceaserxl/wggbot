import discord
from discord import app_commands
from .chatgpt import (
    handle_dm_message,
    handle_chat_command,
    generate_and_send_image
)


# -------------------------------------------------------------------
# SETUP FUNCTION (main.py loader will call this)
# -------------------------------------------------------------------
def setup(bot: discord.Client):

    # ============================================================
    # /chat — ChatGPT text chat
    # ============================================================
    @bot.tree.command(
        name="chat",
        description="Chat with ChatGPT using a prompt."
    )
    async def chat(interaction: discord.Interaction, prompt: str):
        print("Executing /chat")

        if isinstance(interaction.channel, discord.DMChannel):
            await interaction.response.send_message(
                "Just type normally; no command needed.",
                ephemeral=True
            )
            return

        await interaction.response.defer()
        await handle_chat_command(interaction, prompt, bot)



    # ============================================================
    # /image — DALL·E image generation
    # ============================================================
    @bot.tree.command(
        name="image",
        description="Generate an image using DALL·E."
    )
    async def image(interaction: discord.Interaction, prompt: str):
        print("Executing /image")

        await interaction.response.defer(thinking=True)
        await generate_and_send_image(interaction, prompt)



    # ============================================================
    # DM event handler (Monkey-patch onto bot for loader usage)
    # ============================================================
    @bot.event
    async def on_message(message):
        # Skip self
        if message.author == bot.user:
            return

        # DM ChatGPT handling
        if isinstance(message.channel, discord.DMChannel):
            await handle_dm_message(message)
            return

        await bot.process_commands(message)
