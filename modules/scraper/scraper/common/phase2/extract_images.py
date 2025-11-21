import re
from pathlib import Path
from urllib.parse import urljoin
from scraper.common.common import BASE_DOMAIN

# ============================================================
#  DEBUG TOGGLE
# ============================================================
debug = True   # ← set False to disable debug output entirely

# Path: scraper/common/phase2/phase2_debug.txt
DEBUG_PATH = Path(__file__).resolve().parent / "phase2_debug.txt"


def dlog(msg: str):
    """Write debug messages only when debug=True."""
    if not debug:
        return
    with open(DEBUG_PATH, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


# ============================================================
#  IMAGE EXTRACTION
# ============================================================
IMAGE_EXT_PATTERN = r"\.(jpg|jpeg|png|gif|webp|avif)(?=[^a-zA-Z0-9]|$)"


async def extract_images_from_boxes(boxes):
    urls = set()

    dlog("\n================ EXTRACT IMAGES ================\n")

    for box_i, box in enumerate(boxes, start=1):
        imgs = await box.query_selector_all("img")

        if not imgs:
            dlog(f"[box {box_i}] NO img tags found")
            continue

        dlog(f"[box {box_i}] {len(imgs)} <img> tags found")

        for img_i, img in enumerate(imgs, start=1):

            src = await img.get_attribute("src")
            ds  = await img.get_attribute("data-src")

            dlog(f"[box {box_i}][img {img_i}] src= {src}")
            dlog(f"[box {box_i}][img {img_i}] data-src= {ds}")

            # Use data-src if needed
            if (not src) or ("blank.gif" in (src or "")):
                if ds:
                    dlog(f"[box {box_i}][img {img_i}] using data-src")
                    src = ds

            if not src:
                dlog(f"[box {box_i}][img {img_i}] SKIP (no src or data-src)")
                continue

            raw = src

            # Skip junk UI items
            junk_words = ["logo", "placeholder", "blank.gif", "icon-play.svg"]
            if any(j in raw.lower() for j in junk_words):
                dlog(f"[box {box_i}][img {img_i}] SKIP (junk UI): {raw}")
                continue

            # Normalize minimal
            normalized = raw

            if normalized.startswith("//"):
                normalized = "https:" + normalized
                dlog(f"[box {box_i}][img {img_i}] normalized → {normalized}")

            elif not normalized.startswith("http"):
                normalized = urljoin(BASE_DOMAIN, normalized)
                dlog(f"[box {box_i}][img {img_i}] relative → {normalized}")

            # Require real extension
            if not re.search(IMAGE_EXT_PATTERN, normalized, flags=re.IGNORECASE):
                dlog(f"[box {box_i}][img {img_i}] SKIP (no valid ext): {normalized}")
                continue

            dlog(f"[box {box_i}][img {img_i}] ACCEPTED → {normalized}")
            urls.add(normalized)

    dlog(f"[extract_images] FINAL COUNT = {len(urls)}\n")

    return list(urls)
