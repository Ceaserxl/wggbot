# ============================================================
#  FILE: scraper/common/settings.py
#  Handles settings.ini creation, parsing, and global export.
# ============================================================

import os
from pathlib import Path
import configparser


# ============================================================
#  PATH ROOTS
# ============================================================
SCRAPER_ROOT = Path(__file__).resolve().parent.parent      # /scraper
SETTINGS_PATH = SCRAPER_ROOT / "settings.ini"

# Platform-aware download directory
if os.name == "nt":
    download_path = SCRAPER_ROOT / "downloads_win"
else:
    download_path = SCRAPER_ROOT / "downloads"

download_path.mkdir(exist_ok=True)

# Cache directory (JSON shard system or DB can sit here)
CACHE_DIR = SCRAPER_ROOT / "cache"
CACHE_DIR.mkdir(exist_ok=True)


# ============================================================
#  DEFAULT INI CONTENT (Matches YOUR EXACT format)
# ============================================================
DEFAULT_GLOBALS = {
    "required_min_boxes": "1",
    "days_cache_valid":   "70",

    "dry_run":      "false",
    "interwoven":   "false",
    "big_to_small": "false",

    "videos_only":  "false",
    "images_only":  "false",
}

DEFAULT_PHASE1 = {
    "concurrent_scan_tags": "25",
}

DEFAULT_PHASE2 = {
    "concurrent_scan_galleries": "15",
}

DEFAULT_PHASE3 = {
    "concurrent_galleries":          "1",
    "concurrent_images_per_gallery": "50",
    "concurrent_videos_per_gallery": "10",
}


# ============================================================
#  Ensure INI Exists
# ============================================================
def ensure_settings_file():
    if SETTINGS_PATH.exists():
        return

    cfg = configparser.ConfigParser()
    cfg["globals"] = DEFAULT_GLOBALS
    cfg["phase1"]  = DEFAULT_PHASE1
    cfg["phase2"]  = DEFAULT_PHASE2
    cfg["phase3"]  = DEFAULT_PHASE3

    with open(SETTINGS_PATH, "w") as f:
        cfg.write(f)


# ============================================================
#  Helpers
# ============================================================
def _b(v: str) -> bool:
    return str(v).lower() in ("1", "true", "yes", "on")


# ============================================================
#  Main Settings Loader
# ============================================================
def load_settings():
    ensure_settings_file()

    cfg = configparser.ConfigParser()
    cfg.read(SETTINGS_PATH)

    g  = cfg["globals"]
    p1 = cfg["phase1"]
    p2 = cfg["phase2"]
    p3 = cfg["phase3"]

    return {
        # --------- globals ---------
        "required_min_boxes": int(g.get("required_min_boxes", "1")),
        "days_cache_valid":   int(g.get("days_cache_valid", "70")),
        "dry_run":            _b(g.get("dry_run", "false")),
        "interwoven":         _b(g.get("interwoven", "false")),
        "big_to_small":       _b(g.get("big_to_small", "false")),
        "videos_only":        _b(g.get("videos_only", "false")),
        "images_only":        _b(g.get("images_only", "false")),

        # --------- phase1 ---------
        "concurrent_scan_tags": int(p1.get("concurrent_scan_tags", "25")),

        # --------- phase2 ---------
        "concurrent_scan_galleries": int(p2.get("concurrent_scan_galleries", "15")),

        # --------- phase3 ---------
        "concurrent_galleries":          int(p3.get("concurrent_galleries", "1")),
        "concurrent_images_per_gallery": int(p3.get("concurrent_images_per_gallery", "50")),
        "concurrent_videos_per_gallery": int(p3.get("concurrent_videos_per_gallery", "10")),
    }


# ============================================================
#  Export Settings into Global Variables
# ============================================================
def load_global_defaults():
    """
    Load settings.ini into module-level globals
    for use everywhere in the scraper.
    """

    global REQUIRED_MIN_BOXES
    global DAYS_CACHE_VALID
    global DRY_RUN
    global INTERWOVEN_MODE
    global BIG_TO_SMALL
    global VIDEOS_ONLY
    global IMAGES_ONLY

    global SCAN_TAGS_CONC
    global SCAN_GALLS_CONC

    global GALLERY_CONC
    global IMG_CONC
    global VID_CONC

    s = load_settings()

    # --------- globals ---------
    REQUIRED_MIN_BOXES = s["required_min_boxes"]
    DAYS_CACHE_VALID   = s["days_cache_valid"]
    DRY_RUN            = s["dry_run"]
    INTERWOVEN_MODE    = s["interwoven"]
    BIG_TO_SMALL       = s["big_to_small"]
    VIDEOS_ONLY        = s["videos_only"]
    IMAGES_ONLY        = s["images_only"]

    # --------- phase1 ---------
    SCAN_TAGS_CONC = s["concurrent_scan_tags"]

    # --------- phase2 ---------
    SCAN_GALLS_CONC = s["concurrent_scan_galleries"]

    # --------- phase3 ---------
    GALLERY_CONC = s["concurrent_galleries"]
    IMG_CONC     = s["concurrent_images_per_gallery"]
    VID_CONC     = s["concurrent_videos_per_gallery"]


# ============================================================
#  Exports
# ============================================================
__all__ = [
    "SETTINGS_PATH",
    "download_path",
    "CACHE_DIR",
    "ensure_settings_file",
    "load_settings",
    "load_global_defaults",

    "REQUIRED_MIN_BOXES",
    "DAYS_CACHE_VALID",
    "DRY_RUN",
    "INTERWOVEN_MODE",
    "BIG_TO_SMALL",
    "VIDEOS_ONLY",
    "IMAGES_ONLY",

    "SCAN_TAGS_CONC",
    "SCAN_GALLS_CONC",
    "GALLERY_CONC",
    "IMG_CONC",
    "VID_CONC",
]
