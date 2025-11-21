# ============================================================
#  FILE: scraper/common/phase2/extract_videos.py
#  Phase 2B — Extract video PAGE URLs (ASYNC VERSION)
# ============================================================
import re
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from scraper.common.common import BASE_DOMAIN

# ============================================================
#  DEBUG
# ============================================================
debug = True
PHASE2_DIR = Path(__file__).resolve().parent
PHASE2_DEBUG_FILE = PHASE2_DIR / "phase2_debug.txt"

def dlog(*args):
    if not debug:
        return
    try:
        with open(PHASE2_DEBUG_FILE, "a", encoding="utf-8") as f:
            f.write(" ".join(str(a) for a in args) + "\n")
    except:
        pass

# ============================================================
#  ASYNC Phase 2B — Extract VIDEO PAGE URLs from HTML strings
# ============================================================
async def extract_videos_from_boxes(snippets: list[str]) -> list[str]:
    """
    Async wrapper so Phase 2B can be awaited.
    Parsing is synchronous, but async main pipeline expects await.
    """

    video_pages = set()
    dlog("\n================ PHASE 2B: EXTRACT VIDEOS ================\n")

    for box_i, html in enumerate(snippets, start=1):
        soup = BeautifulSoup(html, "html.parser")

        # --------------------------------------------------------
        # Detect play icon inside <img> tags
        # --------------------------------------------------------
        has_play = soup.find("img", src=lambda s: s and "icon-play.svg" in s)
        dlog(f"[box {box_i}] has_play_icon = {bool(has_play)}")

        if not has_play:
            continue

        # --------------------------------------------------------
        # Extract <a href="...">
        # --------------------------------------------------------
        a = soup.find("a", href=True)
        if not a:
            dlog(f"[box {box_i}] SKIP — no <a> tag")
            continue

        href = a.get("href", "").strip()
        dlog(f"[box {box_i}] href = {href}")

        if not href:
            dlog(f"[box {box_i}] SKIP — blank href")
            continue

        # --------------------------------------------------------
        # Normalize URL
        # --------------------------------------------------------
        if href.startswith("//"):
            href = "https:" + href
        elif href.startswith("/"):
            href = BASE_DOMAIN + href
        elif not href.startswith("http"):
            href = urljoin(BASE_DOMAIN, href)

        dlog(f"[box {box_i}] ACCEPTED video page → {href}")
        video_pages.add(href)

    dlog(f"[extract_videos] FINAL COUNT = {len(video_pages)}\n")
    return list(video_pages)
