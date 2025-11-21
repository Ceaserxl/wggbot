# modules/stablediffusion/commands.py

import discord
from discord import app_commands

from .stablediffusion import imagine_command, UpscaleButton


# ------------------------------------------------------------
# setup(bot) — autoloaded by your dynamic main.py
# ------------------------------------------------------------
def setup(bot):

    @bot.tree.command(
        name="imagine",
        description="Generate an image using Stable Diffusion"
    )
    @app_commands.choices(
        size=[
            app_commands.Choice(name="Square", value="512x512"),
            app_commands.Choice(name="Portrait", value="512x768"),
            app_commands.Choice(name="Landscape", value="768x512"),
            app_commands.Choice(name="Square 2x", value="1024x1024"),
            app_commands.Choice(name="Portrait 2x", value="1024x1536"),
            app_commands.Choice(name="Landscape 2x", value="1536x1024"),
        ]
    )
    @app_commands.choices(
        model=[
            app_commands.Choice(name="dynavisionXLAllInOneStylized_releaseV0610Bakedvae",   value="dynavisionXLAllInOneStylized_releaseV0610Bakedvae"),
            app_commands.Choice(name="waiNSFWIllustrious_v120",                             value="waiNSFWIllustrious_v120"),
            app_commands.Choice(name="illustrij_v13",                                       value="illustrij_v13"),
            app_commands.Choice(name="cyberrealisticPony_v11",                              value="cyberrealisticPony_v11"),
            app_commands.Choice(name="illustriousRealismBy_v10",                            value="illustriousRealismBy_v10"),
            app_commands.Choice(name="realDream_sdxlPony15",                                value="realDream_sdxlPony15"),
            app_commands.Choice(name="realisticVisionV60B1_v51HyperVAE",                    value="realisticVisionV60B1_v51HyperVAE"),
            app_commands.Choice(name="revAnimated_v2RebirthVAE",                            value="revAnimated_v2RebirthVAE"),
            app_commands.Choice(name="dreamshaper_8",                                       value="dreamshaper_8"),
            app_commands.Choice(name="disneyPixarCartoon_v10",                              value="disneyPixarCartoon_v10"),
        ]
    )
    async def imagine(
        interaction: discord.Interaction,
        prompt: str,
        size: str = "512x512",
        model: str = "dynavisionXLAllInOneStylized_releaseV0610Bakedvae",
        seed: int = -1,
        gpt: bool = False
    ):
        await imagine_command(
            interaction,
            prompt,
            size,
            model,
            refiner=False,
            seed=seed,
            gpt=gpt
        )
