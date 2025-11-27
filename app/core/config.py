# app/core/config.py

import os
import configparser
from .logging import log, sublog

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
INI_PATH = os.path.join(BASE, "settings.ini")

config = configparser.ConfigParser()

# Load settings.ini once
if os.path.exists(INI_PATH):
    try:
        config.read(INI_PATH)
        log(f"[OK] Loaded settings.ini from {INI_PATH}")
    except Exception as e:
        log(f"[ERR] Failed reading settings.ini: {e}")
else:
    log(f"[WARN] settings.ini not found at: {INI_PATH}")


# ============================================================
# GLOBAL ensure_settings() — used by ALL modules
# ============================================================
def ensure_settings(section: str, defaults: dict):
    """
    Ensures [section] exists in settings.ini and contains all default values.
    Called by modules like:
        ensure_settings("musicplayer", DEFAULTS)
    """

    sublog(f"[CFG] Ensuring [{section}]...")

    updated = False

    # Ensure section exists
    if section not in config:
        config[section] = {}
        updated = True
        sublog(f"[CFG]   Added missing section [{section}]")

    # Ensure default keys
    for key, value in defaults.items():
        if key not in config[section]:
            config[section][key] = value
            updated = True
            sublog(f"[CFG]   Inserted default {key} = {value}")

    # Save file if updated
    if updated:
        try:
            with open(INI_PATH, "w") as f:
                config.write(f)
            sublog(f"[CFG]   Saved updated settings.ini")
        except Exception as e:
            sublog(f"[ERR]   Failed writing settings.ini: {e}")

    sublog(f"[CFG] [{section}] ensured.")

# ============================================================
# Access helpers
# ============================================================

def cfg(section, key, fallback=None):
    try:
        value = config.get(section, key, fallback=fallback)
        sublog(f"[CFG] {section}.{key} = {value}")
        return value
    except Exception as e:
        sublog(f"[ERR] cfg() failed for {section}.{key}: {e}")
        return fallback


def cfg_bool(section, key, fallback=False):
    try:
        value = config.getboolean(section, key, fallback=fallback)
        sublog(f"[CFG] {section}.{key} (bool) = {value}")
        return value
    except Exception as e:
        sublog(f"[ERR] cfg_bool() failed for {section}.{key}: {e}")
        return fallback
