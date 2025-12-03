# /app/modules/stablediffusion/__init__.py
from core.config import ensure_settings
from core.logging import sublog

# ============================================================
# SETTINGS
# ============================================================
DEFAULTS = {
    "sd_host": "http://127.0.0.1:8188",
    "default_width": "512",
    "default_height": "512",
    "default_steps": "4",
    "default_seed": "0",
}

# ============================================================
# init(bot) — called by module loader
# ============================================================
def init(bot):
    sublog("[stablediffusion] initializing...")
    ensure_settings("stablediffusion", DEFAULTS)
    sublog("[stablediffusion] module ready.")
