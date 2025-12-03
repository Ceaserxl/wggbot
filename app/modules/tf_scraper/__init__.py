# app/modules/scraper/__init__.py

# ============================================================
# DEFAULT SETTINGS (used by ensure_settings)
# ============================================================
DEFAULTS = {
    "required_min_boxes": "1",
    "days_cache_valid": "70",

    "dry_run": "false",
    "interwoven": "false",
    "big_to_small": "false",

    "videos_only": "false",
    "images_only": "false",

    "concurrent_scan_tags": "25",
    "concurrent_scan_galleries": "15",

    "concurrent_galleries": "1",
    "concurrent_images_per_gallery": "50",
    "concurrent_videos_per_gallery": "10",
}

# These will be filled by init()
settings = {}

# ============================================================
# MODULE INIT — ONLY RUNS WHEN MODULE LOADER CALLS init(bot)
# ============================================================
def init(bot):
    from app.core.config import ensure_settings, cfg
    from app.core.logging import log, sublog
    global settings
    # Inject defaults into settings.ini if missing
    ensure_settings("scraper", DEFAULTS)
    # Load all scraper config values
    #settings = {key: cfg("scraper", key, DEFAULTS[key])
    #            for key in DEFAULTS}
    sublog("[scraper] settings loaded.")
