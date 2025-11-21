# modules/scraper/commands.py

import discord
from discord import app_commands

from .scraper.main import main as run_scraper   # async main()


def setup(bot):

    @bot.tree.command(
        name="scrape",
        description="Run the TheFap scraper with space-separated tags."
    )
    @app_commands.describe(
        tags="Space-separated tags, e.g. bhabie thick blonde"
    )
    async def scrape_cmd(
        interaction: discord.Interaction,
        tags: str
    ):
        """
        Example:
            /scrape tags:"bhabie thick blonde"
        """

        await interaction.response.defer(thinking=True)

        # Split by spaces
        normalized_tags = [t.strip() for t in tags.split(" ") if t.strip()]

        if not normalized_tags:
            await interaction.followup.send("❌ No valid tags provided.")
            return

        status_msg = await interaction.followup.send(
            f"🚀 **Scraper started**\n"
            f"**Tags:** `{', '.join(normalized_tags)}`\n"
            f"**Mode:** images+videos (default)\n\n"
            "This may take a while…"
        )

        try:
            # Call scraper with correct parameters
            await run_scraper(
                normalized_tags,   # tags list
                [],                # galleries (unused)
                "both",            # mode
                False,             # reverse_flag
                False,             # simulate_flag
                False,             # images_videos_flag
                True               # summary_flag
            )

            await status_msg.edit(
                content=(
                    f"✅ **Scrape complete!**\n"
                    f"Tags: `{', '.join(normalized_tags)}`\n"
                    "Downloads saved."
                )
            )

        except Exception as e:
            await status_msg.edit(
                content=f"❌ **Scraper crashed:**\n```\n{str(e)}\n```"
            )
