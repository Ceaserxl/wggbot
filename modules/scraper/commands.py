import discord
from discord import app_commands

# Import scraper internals
from .scraper.main import (
    load_global_defaults,
    ensure_settings_file,
    cache_db,
    main as run_scraper,
)

def setup(bot):

    @bot.tree.command(
        name="scrape",
        description="Run the scraper with space-separated tags."
    )
    @app_commands.describe(tags="Example: bhabie thick blonde")
    async def scrape_cmd(interaction: discord.Interaction, tags: str):

        await interaction.response.defer(thinking=True)

        normalized = [t for t in tags.split(" ") if t]

        if not normalized:
            return await interaction.followup.send("❌ No tags provided.")

        # Init environment
        ensure_settings_file()
        await cache_db.init_db()
        load_global_defaults()

        msg = await interaction.followup.send("⏳ Starting scraper…")

        try:
            await run_scraper(
                normalized,
                [],
                "both",
                False,   # reverse
                False,   # simulate
                False,   # images_videos
                True     # summary
            )
            await msg.edit(content="✅ Done.")
        except Exception as e:
            await msg.edit(content=f"❌ Error:\n```\n{e}\n```")
