# modules/scraper/__init__.py

import os
import configparser
from datetime import datetime

SETTINGS_PATH = "settings.ini"
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "module_scraper.log")

# Default values to inject if missing
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

# -----------------------------------------------------
# Logging
# -----------------------------------------------------
def log(msg: str):
    os.makedirs(LOG_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")

# -----------------------------------------------------
# Ensure settings.ini has scraper defaults
# -----------------------------------------------------
def ensure_settings():
    config = configparser.ConfigParser()

    if not os.path.exists(SETTINGS_PATH):
        log("settings.ini not found — skipping scraper initialization.")
        return None

    config.read(SETTINGS_PATH)

    # Ensure section exists
    if "scraper" not in config:
        config["scraper"] = {}
        log("Added missing [scraper] section.")

    # Insert defaults when missing
    updated = False
    for key, value in DEFAULTS.items():
        if key not in config["scraper"]:
            config["scraper"][key] = value
            updated = True
            log(f"Inserted default key: {key}={value}")

    # Save changes
    if updated:
        with open(SETTINGS_PATH, "w") as f:
            config.write(f)
        log("Saved updated scraper settings to settings.ini.")

    return config

# -----------------------------------------------------
# init(bot) — called by module_loader
# -----------------------------------------------------
def init(bot):
    log("Initializing Scraper module...")
    ensure_settings()
    log("Scraper module initialization complete.")