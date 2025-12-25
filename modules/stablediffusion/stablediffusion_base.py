# /app/modules/stablediffusion/stablediffusion_base.py

import os
import io
import json
import asyncio
import urllib.parse
import requests
import discord
import random

from core.logging import log
from core.config import cfg


# ============================================================
# CONFIG
# ============================================================
SETTINGS_SECTION = "stablediffusion"

WORKFLOW_PATH = "app/modules/stablediffusion/workflows/default.json"


# ============================================================
# LOAD SETTINGS (NO ensure_settings)
# ============================================================
def load_sd_config():
    return {
        "host": cfg(SETTINGS_SECTION, "sd_host", "http://127.0.0.1:8188").rstrip("/"),
    }


# ============================================================
# WORKFLOW PREPARATION (ONLY MODIFY NODE 56)
# ============================================================
def load_and_patch_workflow(prompt: str):
    if not os.path.exists(WORKFLOW_PATH):
        raise FileNotFoundError(f"Workflow file not found: {WORKFLOW_PATH}")

    with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
        graph = json.load(f)

    save_node_id = None

    for node_id, node in graph.items():
        inputs = node.get("inputs", {})
        ctype = node.get("class_type", "")

        # ---- ONLY update node 56 ----
        if node_id == "56" and "value" in inputs:
            inputs["value"] = prompt
        if node_id == "155" and "value" in inputs:
            inputs["value"] = random.randint(1, 2_147_483_647)

        # ---- Find SaveImage node ----
        if ctype == "SaveImage":
            save_node_id = node_id

    if not save_node_id:
        raise RuntimeError("SaveImage node not found in workflow.")

    return graph, save_node_id


# ============================================================
# COMFYUI HELPERS
# ============================================================
async def post_prompt(host: str, graph: dict) -> str:
    url = f"{host}/prompt"

    def _task():
        r = requests.post(url, json={"prompt": graph, "client_id": "discord-sd"}, timeout=600)
        r.raise_for_status()
        return r.json()

    data = await asyncio.to_thread(_task)
    pid = data.get("prompt_id")
    if not pid:
        raise RuntimeError("ComfyUI did not return prompt_id")
    return pid


async def wait_for_history(host: str, pid: str, timeout=240):
    url = f"{host}/history/{pid}"
    end = asyncio.get_event_loop().time() + timeout

    while True:
        if asyncio.get_event_loop().time() > end:
            raise TimeoutError("Timed out waiting for ComfyUI history.")

        def _task():
            r = requests.get(url, timeout=30)
            if r.status_code == 404:
                return None
            try:
                r.raise_for_status()
                return r.json()
            except:
                return None

        history = await asyncio.to_thread(_task)

        if history and pid in history and "outputs" in history[pid]:
            return history[pid]

        await asyncio.sleep(0.25)


async def fetch_image_bytes(host: str, history: dict, save_node_id: str) -> bytes:
    out = history["outputs"][str(save_node_id)]["images"][0]

    query = urllib.parse.urlencode({
        "filename": out["filename"],
        "subfolder": out.get("subfolder", ""),
        "type": out.get("type", "output"),
    })

    url = f"{host}/view?{query}"

    def _task():
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        return r.content

    return await asyncio.to_thread(_task)


# ============================================================
# PUBLIC /imagine ENTRY
# ============================================================
async def imagine_command(interaction: discord.Interaction, prompt: str):
    sd = load_sd_config()

    log(f"[stablediffusion] /imagine by {interaction.user} — {prompt!r}")

    graph, save_node_id = load_and_patch_workflow(prompt)

    pid = await post_prompt(sd["host"], graph)
    log(f"[stablediffusion] submitted prompt_id {pid}")

    history = await wait_for_history(sd["host"], pid)
    log(f"[stablediffusion] history ready for {pid}")

    img_bytes = await fetch_image_bytes(sd["host"], history, save_node_id)

    file = discord.File(io.BytesIO(img_bytes), filename="image.png")

    await interaction.followup.send(
        content=f"🖼️ **Prompt:** `{prompt}`",
        file=file
    )

    log("[stablediffusion] image delivered.")
