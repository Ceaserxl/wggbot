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
        description="Generate an image using Stable Diffusion (512x512)."
    )
    async def imagine_cmd(
        interaction: discord.Interaction,
        prompt: str
    ):

        # Block DMs just like your music commands
        if isinstance(interaction.channel, discord.DMChannel):
            return await interaction.response.send_message(
                "❌ This command cannot be used in DMs.",
                ephemeral=True
            )

        await interaction.response.defer()
        msg = await interaction.followup.send("🖼️ Generating image...")

        try:
            await imagine_command(interaction, prompt)
        except Exception as e:
            await msg.edit(content=f"❌ Error: {e}")
