# ============================================================
#  FILE: scraper/common/phase2/extract_images.py
#  Phase 2A — Extract image URLs from HTML snippets
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
#  Phase 2A — Extract image URLs from HTML STRINGS
# ============================================================
async def extract_images_from_boxes(snippets):
    """
    Phase 2A receives HTML *strings* (from Phase 1B).
    We no longer require extensions — download first, detect later.
    """
    urls = set()
    dlog("\n================ PHASE 2A: EXTRACT IMAGES ================\n")

    for box_i, html in enumerate(snippets, start=1):
        soup = BeautifulSoup(html, "html.parser")
        imgs = soup.find_all("img")

        if not imgs:
            dlog(f"[box {box_i}] NO <img> tags found")
            continue

        for img_i, img in enumerate(imgs, start=1):
            src = img.get("src")
            ds  = img.get("data-src")

            # Prefer data-src if usable
            if not src or "blank.gif" in (src or ""):
                if ds:
                    src = ds
                    dlog(f"[box {box_i}][img {img_i}] using data-src")

            if not src:
                dlog(f"[box {box_i}][img {img_i}] SKIP (no usable src)")
                continue

            raw = src

            # Skip junk UI assets
            junk_words = ["logo", "placeholder", "blank.gif", "icon-play.svg"]
            if any(j in raw.lower() for j in junk_words):
                dlog(f"[box {box_i}][img {img_i}] SKIP (junk UI): {raw}")
                continue

            # Normalize minimal
            normalized = raw

            if normalized.startswith("//"):
                normalized = "https:" + normalized
                dlog(f"[box {box_i}][img {img_i}] protocol-relative → {normalized}")

            elif not normalized.startswith("http"):
                normalized = urljoin(BASE_DOMAIN, normalized)
                dlog(f"[box {box_i}][img {img_i}] relative → {normalized}")

            # No extension checks — allow everything
            dlog(f"[box {box_i}][img {img_i}] ACCEPTED (no-ext OK) → {normalized}")
            urls.add(normalized)

    dlog(f"[extract_images] FINAL COUNT = {len(urls)}\n")
    return list(urls)
