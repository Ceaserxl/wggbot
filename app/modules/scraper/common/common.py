# ============================================================
#  common.py — Shared Utilities
#  Location: scraper/common/common.py
# ============================================================

import os
import re
import base64
import signal
import sys
import threading
import asyncio
import requests

from io import StringIO
from rich.console import Console
from bs4 import BeautifulSoup
from tqdm import tqdm
from playwright.async_api import async_playwright


# ============================================================
#  GLOBAL CONSTANTS
# ============================================================
BASE_URL = "https://thefap.net/search/{}/"
BASE_DOMAIN = "https://thefap.net"
HEADERS = {"User-Agent": "Mozilla/5.0 (CeaserXL-Async/1.0)"}

BANNER_WIDTH = 60


# ============================================================
#  THREAD-SAFE PRINTING (supports Rich + tqdm)
# ============================================================
_print_lock = threading.Lock()

def safe_print(*args, **kwargs):
    """Thread-safe Rich print that does not break tqdm bars."""
    with _print_lock:
        buf = StringIO()
        tmp = Console(
            file=buf,
            force_terminal=True,
            color_system="auto",
        )
        tmp.print(*args, **kwargs)
        out = buf.getvalue().rstrip("\n")
        tqdm.write(out)


# ============================================================
#  BANNERS
# ============================================================
def _banner_block(title, emoji, width, char):
    border = char * width
    center = title.center(width).ljust(width)
    safe_print(f"{emoji} {border} {emoji}")
    safe_print(f"{emoji} {center} {emoji}")
    safe_print(f"{emoji} {border} {emoji}")


def print_banner(title, emoji="🔷", char="═", min_width=BANNER_WIDTH):
    width = max(min_width, len(title) + 8)
    _banner_block(title, emoji, width, char)


def print_subbanner(title, emoji="📁", char="─", min_width=BANNER_WIDTH):
    width = max(min_width, len(title) + 8)
    _banner_block(title, emoji, width, char)


def print_summary(*lines, emoji="📄", char="═", min_width=BANNER_WIDTH):
    max_len = max((len(line) for line in lines), default=0)
    width = max(min_width, max_len + 8)

    border = char * width
    safe_print(f"{emoji} {border} {emoji}")
    for line in lines:
        center = line.center(width).ljust(width)
        safe_print(f"{emoji} {center} {emoji}")
    safe_print(f"{emoji} {border} {emoji}")


# ============================================================
#  IMAGE URL CLEANUP
# ============================================================
def sanitize_image_url(url: str) -> str:
    """Cleanup CDN scaling modifiers (:small?w=600, ?w=1200, etc.)."""
    if not url:
        return url

    url = re.sub(r":[a-z]+(\?.*)?$", lambda m: m.group(1) or "", url)
    url = re.sub(r"\?w=\d+$", "", url)
    return url


# ============================================================
#  VIDEO HELPERS
# ============================================================
def decode_file_param(raw: str) -> str | None:
    """Extract real URL from file= parameter (base64 or raw)."""
    if not raw:
        return None

    if raw.startswith("http"):
        return raw

    try:
        decoded = base64.b64decode(raw).decode(errors="ignore")
        if decoded.startswith("http"):
            return decoded
    except Exception:
        pass

    return None


# ============================================================
#  SEARCH UTILITIES (manual only)
# ============================================================
def get_search_results(term: str):
    """Manual search scraper (used only for debugging)."""
    results = set()
    page = 1

    while True:
        url = f"{BASE_DOMAIN}/search/{term}/{page}/"
        print(f"🔎 Searching page {page}: {url}")

        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                break
        except Exception:
            print(f"    ❌ Request failed on page {page}.")
            break

        soup = BeautifulSoup(r.text, "html.parser")
        links = [
            BASE_DOMAIN + a["href"]
            for a in soup.select("a[href^='/']")
            if re.search(r"-\d+/?$", a["href"])
        ]

        old = len(results)
        results.update(links)

        if len(results) == old:
            break

        page += 1

    print(f"✅ {len(results)} galleries found for '{term}'")
    return list(results)


# ============================================================
#  Chromium Launcher (Playwright)
# ============================================================
async def launch_chromium(user_data_dir: str | None = None, headless: bool = True):
    """Launch high-performance Chromium for scraping."""
    gpu_flags = [
        "--enable-gpu",
        "--ignore-gpu-blocklist",
        "--use-gl=desktop",
        "--enable-gpu-rasterization",
        "--enable-zero-copy",
        "--enable-accelerated-video-decode",
        "--disable-dev-shm-usage",
        "--disable-default-apps",
        "--no-sandbox",
    ]

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=headless, args=gpu_flags)
    context = await browser.new_context()
    return pw, context


# ============================================================
#  CTRL+C HANDLER
# ============================================================
stop_event = asyncio.Event()

def _sigint_handler(signum, frame):
    print("\n🛑 Ctrl+C detected — killing all tasks...")
    stop_event.set()

    for t in asyncio.all_tasks():
        t.cancel()

    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(1)


signal.signal(signal.SIGINT, _sigint_handler)
signal.signal(signal.SIGTERM, _sigint_handler)
