# ============================================================
#  FILE: scraper/common/phase2/extract_videos.py
#  Phase 2B — Extract VIDEO PAGE URLs (ASYNC, INDEX-PRESERVING)
# ============================================================

import re
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from scraper.common.common import BASE_DOMAIN

# ============================================================
#  DEBUG
# ============================================================
debug = False
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
#  ASYNC Phase 2B — Extract + DE-DUPLICATE video PAGE URLs
# ============================================================
async def extract_videos_from_boxes(snippets):
    """
    Input:
        snippets = [(idx, outerHTML), ...]

    Output:
        [(idx, video_page_url), ...] — unique, index-preserving
    """

    dlog("\n================ PHASE 2B: EXTRACT VIDEOS ================\n")

    # Dedup container:
    # key = (box_idx, normalized_url)
    dedup = {}

    for box_idx, html in snippets:
        soup = BeautifulSoup(html, "html.parser")

        # Detect play icon
        has_play = soup.find("img", src=lambda s: s and "icon-play.svg" in s)
        dlog(f"[box {box_idx}] has_play_icon = {bool(has_play)}")

        if not has_play:
            continue

        # Extract <a href>
        a = soup.find("a", href=True)
        if not a:
            dlog(f"[box {box_idx}] SKIP — no <a> tag")
            continue

        href = a.get("href", "").strip()
        dlog(f"[box {box_idx}] raw href = {href}")

        if not href:
            dlog(f"[box {box_idx}] SKIP — blank href")
            continue

        # Normalize
        if href.startswith("//"):
            href = "https:" + href
        elif href.startswith("/"):
            href = BASE_DOMAIN + href
        elif not href.startswith("http"):
            href = urljoin(BASE_DOMAIN, href)

        dlog(f"[box {box_idx}] ACCEPTED → {href}")

        # DEDUPE HERE
        dedup[(box_idx, href)] = True

    # Convert dedupe dict → stable list
    results = [(idx, href) for (idx, href) in dedup.keys()]
    results.sort(key=lambda x: (x[0], x[1]))

    dlog(f"[extract_videos] FINAL UNIQUE COUNT = {len(results)}\n")
    return results
