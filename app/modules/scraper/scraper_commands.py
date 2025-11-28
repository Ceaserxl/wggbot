# modules/scraper/scraper_commands.py

import discord
from discord import app_commands
#from .scraper_base import main

def register(bot):
    @bot.tree.command(
        name="scrape",
        description="Run the scraper with space-separated tags."
    )
    async def scrape_test(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        await interaction.followup.send("FUCK YOU")