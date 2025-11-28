# modules/stablediffusion/stablediffusion_commands.py

import discord
from discord import app_commands

from .stablediffusion_base import imagine_command


# -------------------------------------------------------------
# register(bot)
# Called automatically by module_loader after init()
# -------------------------------------------------------------
def register(bot):

    # ==========================================================
    # /imagine
    # ==========================================================
    @bot.tree.command(
        name="imagine",
        description="Generate an image using the Stable Diffusion backend."
    )
    @app_commands.describe(
        prompt="Describe what you want the AI to generate."
    )
    async def imagine_cmd(
        interaction: discord.Interaction,
        prompt: str
    ):
        # Prevent DM usage (same behavior as other modules)
        if isinstance(interaction.channel, discord.DMChannel):
            return await interaction.response.send_message(
                "❌ This command cannot be used in DMs.",
                ephemeral=True
            )

        # Initial defer
        await interaction.response.defer()

        # Placeholder message
        msg = await interaction.followup.send("🖼️ Generating image...")

        # Try SD pipeline
        try:
            await imagine_command(interaction, prompt)

        except Exception as e:
            await msg.edit(content=f"❌ Error: {e}")
