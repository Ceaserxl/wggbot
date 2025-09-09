# ── Imports ─────────────────────────────────────────────────────────────
import os, io, time, base64, json, asyncio, requests, aiohttp
from datetime import datetime
import discord
from discord.ui import View
from resources import keys

# ── Configuration ───────────────────────────────────────────────────────
SD_API_URL      = keys.SD_API_URL
HR_SCALE        = 1.5
generation_lock = asyncio.Lock()
pending_messages: list[discord.Message] = []

# ── Prompt Generator via Ollama ─────────────────────────────────────────
async def generate_sd_prompt(prompt: str, model: str = keys.OLLAMA_MODEL) -> tuple[str, str] | tuple[None, None, str]:
    url = f"http://{keys.OLLAMA_IP}:11434/api/generate"
    system_context = (
        "You are a professional Stable Diffusion prompt engineer. "
        "Only generate NSFW content if the user's prompt includes explicit words like 'nude', 'naked', 'topless', or similar. "
        "Otherwise, keep the output strictly SFW. "
        "Only return one line, and it must start exactly like this:\n"
        "Prompt: <comma-separated keywords>\n"
        "Include: subject, anatomy, clothing or nudity, pose, expression, setting, lighting, camera angle, style, and quality tags. "
        "Do not include weights, parentheses, or extra lines. No explanations, no labels, just the line starting with 'Prompt:'."
    )


    full_prompt = f"{system_context}\n\nUser: {prompt}"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                url,
                json={"model": model, "prompt": full_prompt, "stream": False},
                headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status != 200:
                    return None, None, "❌ Ollama returned a non-200 status code."
                data = await resp.json()
                response_text = data.get("response", "")
        except Exception as e:
            return None, None, f"❌ Ollama error: {str(e)}"

    image_prompt = ""
    for line in response_text.splitlines():
        if line.lower().startswith("prompt:"):
            image_prompt = line.split(":", 1)[-1].strip()

    if not image_prompt:
        return None, None, f"❌ Failed to parse prompt from Ollama:\n{response_text.strip()}"

    return image_prompt, "", None  # negative_prompt set to blank

# ── Upscale Button View ─────────────────────────────────────────────────
class UpscaleButton(View):
    def __init__(self, seed, model, prompt, neg_prompt, width, height, filename):
        super().__init__(timeout=None)
        self.seed       = seed
        self.model      = model
        self.prompt     = prompt
        self.neg_prompt = neg_prompt
        self.width      = width
        self.height     = height
        self.filename   = filename

    @discord.ui.button(label="🗑 Delete", style=discord.ButtonStyle.danger)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()

    @discord.ui.button(label="Upscale (1.5×)", style=discord.ButtonStyle.secondary)
    async def upscale(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        progress_msg = interaction.message
        await progress_msg.edit(view=None)
        embed = progress_msg.embeds[0]
        self.clear_items()
        await progress_msg.edit(embed=embed, attachments=[])

        pending_messages.append(progress_msg)
        pos = len(pending_messages)
        embed.title = "🆙 Upscaling 🆙"
        embed.color = discord.Color.blurple()
        embed.description = f"⏳ You are #{pos} in queue. Please wait…"
        embed.set_footer(text="")
        await progress_msg.edit(embed=embed)

        async with generation_lock:
            pending_messages.pop(0)
            for idx, m in enumerate(pending_messages, start=1):
                e = m.embeds[0]
                e.description = f"⏳ You are #{idx} in queue. Please wait…"
                e.set_footer(text="")
                await m.edit(embed=e)

            target_w = int(self.width * HR_SCALE)
            target_h = int(self.height * HR_SCALE)
            embed.title = f"🆙 Upscaling to {target_w}×{target_h} 🆙"
            embed.description = "\n".join([
                f"**Prompt:**\n```{self.prompt}```",
                f"**Model:**\n```{self.model}```"
            ])
            embed.set_footer(text=f"Upscaling... 0.0% • ETA: --s • {target_w}×{target_h}")
            await progress_msg.edit(embed=embed)

            session = requests.Session()
            loop = asyncio.get_running_loop()
            start = time.time()
            path = os.path.join("images", self.filename)
            with open(path, "rb") as f:
                init_b64 = base64.b64encode(f.read()).decode()

            payload = {
                "init_images": [f"data:image/png;base64,{init_b64}"],
                "prompt": self.prompt,
                "negative_prompt": self.neg_prompt,
                "seed": self.seed,
                "steps": 15,
                "sampler_name": "DPM++ 2M",
                "scheduler": "Karras",
                "denoising_strength": 0.7,
                "width": target_w,
                "height": target_h,
                "override_settings": {"sd_model_checkpoint": self.model}
            }

            task = loop.run_in_executor(None, lambda: session.post(f"{SD_API_URL}/sdapi/v1/img2img", json=payload, timeout=999))
            prog_url = f"{SD_API_URL}/sdapi/v1/progress?skip_current_image=false"

            while not task.done():
                pr = session.get(prog_url, timeout=10).json()
                pct = pr.get("progress", 0.0) * 100
                eta = int(pr.get("eta_relative", 0))
                embed.set_footer(text=f"Upscaling... {pct:.1f}% • ETA: {eta}s • {target_w}×{target_h}")

                if img_data := pr.get("current_image"):
                    preview = base64.b64decode(img_data.split(",", 1)[-1])
                    preview_file = discord.File(io.BytesIO(preview), filename="preview.png")
                    embed.set_image(url="attachment://preview.png")
                    await progress_msg.edit(embed=embed, attachments=[preview_file])
                else:
                    await progress_msg.edit(embed=embed)

                await asyncio.sleep(2)

            resp = task.result(); resp.raise_for_status()
            final_bytes = base64.b64decode(resp.json()["images"][0])
            duration = time.time() - start

            final_file = discord.File(io.BytesIO(final_bytes), filename="upscaled.png")
            embed.set_image(url="attachment://upscaled.png")
            embed.set_footer(text=f"Seed: {self.seed} • Time: {duration:.1f}s • {target_w}×{target_h}")
            self.add_item(self.delete)
            await progress_msg.edit(embed=embed, attachments=[final_file], view=self)
            session.close()

# ── /imagine Command Logic ──────────────────────────────────────────────
async def imagine_command(interaction: discord.Interaction, user_prompt: str, size: str, model: str, refiner: bool, seed: int, gpt: bool):
    session = requests.Session()
    await interaction.response.defer()
    neg_prompt = ""
    width, height = {
        "512x512": (512, 512),
        "768x512": (768, 512),
        "512x768": (512, 768),
        "1024x1024": (1024, 1024),
        "1024x1536": (1024, 1536),
        "1536x1024": (1536, 1024),
    }.get(size, (512, 512))

    try:
        session.get(f"{SD_API_URL}/sdapi/v1/sd-models", timeout=2).raise_for_status()
    except requests.RequestException:
        return await interaction.followup.send(
            "⚠️ Stable Diffusion server is currently offline. Please try again later.", ephemeral=True
        )

    # ── Platform-Specific Overrides ─────────────────────────────────────────
    if keys.DEBUG:
        if not gpt:
            user_prompt, neg_prompt, error = user_prompt, "", None #await generate_sd_prompt(user_prompt)
        else:
            user_prompt, neg_prompt, error = await generate_sd_prompt(user_prompt)
        if error:
            return await interaction.followup.send(error)

    await interaction.followup.send(f"⏳ You are #{len(pending_messages)+1} in queue. Please wait…")
    msg = await interaction.original_response()
    pending_messages.append(msg)

    async with generation_lock:
        pending_messages.pop(0)
        for i, m in enumerate(pending_messages, 1):
            await m.edit(content=f"⏳ You are #{i} in queue. Please wait…")

        embed = discord.Embed(
            title="🎨 Generating Image 🎨",
            color=discord.Color.green(),
            description="\n".join([
                f"**Prompt:**\n```{user_prompt}```",
                f"**Model:**\n```{model}```"
            ])
        )
        embed.set_footer(text=f"Progress: 0.0% • ETA: --s • {width}×{height}")
        progress_msg = await msg.edit(content=None, embed=embed)

        start = time.time()
        loop = asyncio.get_running_loop()
        payload = {
            "prompt": user_prompt,
            "negative_prompt": neg_prompt,
            "width": width,
            "height": height,
            "steps": 20,
            "sampler_name": "DPM++ 2M",
            "scheduler": "Karras",
            "hr_scale": HR_SCALE,
            "hr_upscaler": "Latent",
            "hr_second_pass_steps": 10,
            "denoising_strength": 0.7,
            "save_images": True,
            "seed": seed,
            "override_settings": {"sd_model_checkpoint": model}
        }
        if refiner:
            payload.update({
                "enable_refiner": True,
                "refiner_switch_at": 0.8,
                "refiner_checkpoint": "realDream_sdxlRealismRefinerV2.safetensors",
            })

        task = loop.run_in_executor(None, lambda: session.post(
            f"{SD_API_URL}/sdapi/v1/txt2img", json=payload, timeout=999
        ))

        prog_url = f"{SD_API_URL}/sdapi/v1/progress?skip_current_image=false"
        while not task.done():
            pr = session.get(prog_url, timeout=10).json()
            pct = pr.get("progress", 0.0) * 100
            eta = int(pr.get("eta_relative", 0))
            embed.set_footer(text=f"Progress: {pct:.1f}% • ETA: {eta}s • {width}×{height}")
            if img := pr.get("current_image"):
                preview = base64.b64decode(img.split(",", 1)[-1])
                file = discord.File(io.BytesIO(preview), filename="preview.png")
                embed.set_image(url="attachment://preview.png")
                await progress_msg.edit(embed=embed, attachments=[file])
            else:
                await progress_msg.edit(embed=embed)
            await asyncio.sleep(1)

        resp = task.result(); resp.raise_for_status()
        data = resp.json()
        info = json.loads(data.get("info", "{}"))
        used_seed = info.get("seed", "unknown")
        duration = time.time() - start

        final_bytes = base64.b64decode(data["images"][0])
        os.makedirs("images", exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{ts}.png"
        path = os.path.join("images", fname)
        with open(path, "wb") as f:
            f.write(final_bytes)

        file = discord.File(path, filename=fname)
        embed.set_image(url=f"attachment://{fname}")
        embed.set_footer(text=f"Seed: {used_seed} • Time: {duration:.1f}s • {width}×{height}")
        view = UpscaleButton(used_seed, model, user_prompt, neg_prompt, width, height, fname)
        await progress_msg.edit(embed=embed, attachments=[file], view=view)

    session.close()