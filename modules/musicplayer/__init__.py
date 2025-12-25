# /app/modules/musicplayer/__init__.py

from core.logging import log, sublog
from core.config import ensure_settings


# Default settings for the music player module
DEFAULTS = {
    "volume": "50",
    "autojoin": "true",
    "max_queue": "25"
}


def init(bot):
    """Called by module_loader BEFORE commands and setup."""
    # Ask core/config to ensure our settings exist
    ensure_settings("musicplayer", DEFAULTS)