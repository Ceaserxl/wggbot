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
# DEFAULT CONFIG FOR JUGGERNAUT WORKFLOW
# ============================================================
WORKFLOW_PATH = "app/modules/stablediffusion/workflows/juggernautXL_ragnarokBy.json"

DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 1024

DEFAULT_STEPS = 20
DEFAULT_GUIDANCE = 7.5   # SDXL standard


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
# Load + modify JSON workflow (API-ready graph)
# ============================================================
def _load_and_prepare_workflow(prompt: str) -> tuple[dict, str]:
    if not os.path.exists(WORKFLOW_PATH):
        raise FileNotFoundError(f"Workflow file not found: {WORKFLOW_PATH}")

    with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
        graph = json.load(f)

    save_node_id = None
    shared_seed = _random_seed()

    for node_id, node in graph.items():
        ctype = node.get("class_type")

        if ctype == "SaveImage":
            save_node_id = node_id

        # positive prompt (the one that's empty in JSON)
        if ctype == "CLIPTextEncode":
            if node["inputs"].get("text", "") == "":
                node["inputs"]["text"] = prompt

        if ctype == "EmptyLatentImage":
            node["inputs"]["width"] = DEFAULT_WIDTH
            node["inputs"]["height"] = DEFAULT_HEIGHT

        if ctype == "KSampler":
            node["inputs"]["seed"] = shared_seed

    if not save_node_id:
        raise RuntimeError("SaveImage node not found in workflow JSON.")

    return graph, save_node_id


# ============================================================
# ComfyUI HTTP communication
# ============================================================
async def _post_prompt(host: str, graph: dict) -> str:
    url = f"{host}/prompt"

    def _do_post():
        r = requests.post(url, json={"prompt": graph, "client_id": "discord-sdxl"}, timeout=600)
        r.raise_for_status()
        return r.json()

    result = await asyncio.to_thread(_do_post)
    pid = result.get("prompt_id")
    if not pid:
        raise RuntimeError("ComfyUI did not return a prompt_id")
    return pid


async def _wait_for_history(host: str, pid: str, timeout=180):
    url = f"{host}/history/{pid}"
    loop = asyncio.get_event_loop()
    end = loop.time() + timeout

    while True:
        if loop.time() > end:
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
    out = history["outputs"][save_node_id]["images"][0]
    filename = out["filename"]
    subfolder = out.get("subfolder", "")
    imgtype = out.get("type", "output")

    q = urllib.parse.urlencode({
        "filename": filename,
        "subfolder": subfolder,
        "type": imgtype,
    })

    url = f"{host}/view?{q}"

    def _do_get():
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        return r.content

    return await asyncio.to_thread(_do_get)


# ============================================================
# PUBLIC ENTRYPOINT (/imagine)
# ============================================================
async def imagine_command(interaction: discord.Interaction, prompt: str):
    host = _get_sd_host()
    log(f"/imagine invoked by {interaction.user} prompt={prompt!r}")

    # Load and patch workflow
    graph, save_node_id = _load_and_prepare_workflow(prompt)

    # Send to ComfyUI
    pid = await _post_prompt(host, graph)
    log(f"Submitted prompt_id {pid}")

    # Wait for output
    history = await _wait_for_history(host, pid)
    log(f"History ready for {pid}")

    # Fetch image
    img_bytes = await _fetch_image(host, history, save_node_id)

    file = discord.File(io.BytesIO(img_bytes), filename="juggernaut_output.png")

    await interaction.followup.send(
        content=f"🖼️ **Prompt:** `{prompt}`",
        file=file
    )

    log("Image delivered.")
