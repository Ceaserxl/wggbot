import asyncio
import io
import json
import random
import urllib.parse
import os

import discord
import requests

from . import ensure_settings, DEFAULTS, log


# ============================================================
# DEFAULT CONFIG — QWEN WORKFLOW
# ============================================================
WORKFLOW_PATH = "app/modules/stablediffusion/workflows/default.json"

DEFAULT_WIDTH = 768
DEFAULT_HEIGHT = 768


# ============================================================
# Helpers
# ============================================================
def _get_sd_host() -> str:
    cfg = ensure_settings()
    if cfg:
        return cfg["stablediffusion"].get("sd_host", DEFAULTS["sd_host"]).rstrip("/")
    return DEFAULTS["sd_host"]


def _random_seed() -> int:
    return random.randint(1, 2_147_483_647)


# ============================================================
# Load + patch workflow (REAL PROMPT GRAPH)
# ============================================================
def _load_and_prepare_workflow(prompt: str) -> tuple[dict, str]:
    if not os.path.exists(WORKFLOW_PATH):
        raise FileNotFoundError(f"Workflow file not found: {WORKFLOW_PATH}")

    with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
        graph = json.load(f)

    save_node_id = None
    shared_seed = _random_seed()

    # graph is NOT LiteGraph — it's Dict[str, Node]
    for node_id, node in graph.items():
        ctype = node.get("class_type")
        inputs = node.get("inputs", {})

        # ---- SaveImage node -----------------------------------
        if ctype == "SaveImage":
            save_node_id = node_id

        # ---- Positive CLIPTextEncode --------------------------
        if ctype == "CLIPTextEncode":
            # Only one encoder: overwrite text
            if "text" in inputs:
                inputs["text"] = prompt

        # ---- EmptySD3LatentImage width/height -----------------
        if ctype in ("EmptySD3LatentImage", "EmptyLatentImage"):
            if "width" in inputs:
                inputs["width"] = DEFAULT_WIDTH
            if "height" in inputs:
                inputs["height"] = DEFAULT_HEIGHT

        # ---- KSampler: patch seed ------------------------------
        if ctype == "KSampler":
            if "seed" in inputs:
                inputs["seed"] = shared_seed

    if not save_node_id:
        raise RuntimeError("SaveImage node not found in workflow JSON.")

    return graph, save_node_id


# ============================================================
# ComfyUI Communication
# ============================================================
async def _post_prompt(host: str, graph: dict) -> str:
    url = f"{host}/prompt"

    def _do_post():
        r = requests.post(url, json={"prompt": graph, "client_id": "discord-qwen"}, timeout=600)
        r.raise_for_status()
        return r.json()

    data = await asyncio.to_thread(_do_post)
    pid = data.get("prompt_id")
    if not pid:
        raise RuntimeError("ComfyUI did not return prompt_id")
    return pid


async def _wait_for_history(host: str, pid: str, timeout=240):
    url = f"{host}/history/{pid}"
    end = asyncio.get_event_loop().time() + timeout

    while True:
        if asyncio.get_event_loop().time() > end:
            raise TimeoutError("Timed out waiting for ComfyUI history.")

        def _do_get():
            r = requests.get(url, timeout=30)
            if r.status_code == 404:
                return None
            try:
                r.raise_for_status()
                return r.json()
            except:
                return None

        data = await asyncio.to_thread(_do_get)

        if data and pid in data and "outputs" in data[pid]:
            return data[pid]

        await asyncio.sleep(0.25)


async def _fetch_image(host: str, history: dict, save_node_id: str) -> bytes:
    out = history["outputs"][str(save_node_id)]["images"][0]

    q = urllib.parse.urlencode({
        "filename": out["filename"],
        "subfolder": out.get("subfolder", ""),
        "type": out.get("type", "output"),
    })

    url = f"{host}/view?{q}"

    def _do_get():
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        return r.content

    return await asyncio.to_thread(_do_get)


# ============================================================
# PUBLIC ENTRY (/imagine)
# ============================================================
async def imagine_command(interaction: discord.Interaction, prompt: str):
    host = _get_sd_host()
    log(f"/imagine by {interaction.user} prompt={prompt!r}")

    graph, save_node_id = _load_and_prepare_workflow(prompt)

    pid = await _post_prompt(host, graph)
    log(f"Submitted prompt_id {pid}")

    history = await _wait_for_history(host, pid)
    log(f"History ready for {pid}")

    img_bytes = await _fetch_image(host, history, save_node_id)

    file = discord.File(io.BytesIO(img_bytes), filename="default_output.png")

    await interaction.followup.send(
        content=f"🖼️ **Prompt:** `{prompt}`",
        file=file
    )

    log("Image delivered.")
