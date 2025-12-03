# ============================================================
#  FILE: scraper/common/phase2/extract_images.py
#  Phase 2A — Extract image URLs from HTML snippets
# ============================================================

import re
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from tf_scraper.common.common import BASE_DOMAIN

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
#  Phase 2A — Extract + DE-DUPLICATE image URLs
# ============================================================
async def extract_images_from_boxes(snippets):
    """
    Input:
        snippets = [(idx, outerHTML), ...]

    Output:
        [(idx, image_url), ...] — TRUE box index preserved
        Deduplicated by BOTH (idx, url)
    """

    dlog("\n================ PHASE 2A: EXTRACT IMAGES ================\n")

    # We'll accumulate in a dict to dedupe:
    # key = (box_idx, normalized_url)
    dedup = {}

    for (box_idx, html) in snippets:
        soup = BeautifulSoup(html, "html.parser")
        imgs = soup.find_all("img")

        if not imgs:
            dlog(f"[box {box_idx}] NO <img> tags found")
            continue

        for img_i, img in enumerate(imgs, start=1):
            src = img.get("src")
            ds = img.get("data-src")

            # Prefer data-src
            if not src or "blank.gif" in (src or ""):
                if ds:
                    src = ds
                    dlog(f"[box {box_idx}][img {img_i}] using data-src")

            if not src:
                dlog(f"[box {box_idx}][img {img_i}] SKIP (no usable src)")
                continue

            raw = src

            # Skip junk UI elements
            junk_words = ["logo", "placeholder", "blank.gif", "icon-play.svg"]
            if any(j in raw.lower() for j in junk_words):
                dlog(f"[box {box_idx}][img {img_i}] SKIP (junk): {raw}")
                continue

            # Normalize
            normalized = raw

            if normalized.startswith("//"):
                normalized = "https:" + normalized
                dlog(f"[box {box_idx}][img {img_i}] protocol-relative → {normalized}")

            elif not normalized.startswith("http"):
                normalized = urljoin(BASE_DOMAIN, normalized)
                dlog(f"[box {box_idx}][img {img_i}] relative → {normalized}")

            dlog(f"[box {box_idx}][img {img_i}] ACCEPTED → {normalized}")

            # DEDUPE HERE
            dedup[(box_idx, normalized)] = True

    # Convert dedup dict back to list
    results = [(idx, url) for (idx, url) in dedup.keys()]

    # OPTIONAL: sort so results are stable
    results.sort(key=lambda x: (x[0], x[1]))

    dlog(f"[extract_images] FINAL UNIQUE COUNT = {len(results)}\n")
    return results
