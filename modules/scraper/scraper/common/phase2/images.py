# ============================================================
#  images.py — Phase 2 Image Extraction + Download Dispatcher
#  Location: scraper/common/phase2/images.py
# ============================================================

import re
import asyncio
from urllib.parse import urljoin
from tqdm import tqdm

# -----------------------------
# Correct project imports
# -----------------------------
from scraper.common.common import BASE_DOMAIN, safe_print
from scraper.common.phase3.download_file import download_file


# ============================================================
#  Normalize WP / CDN image URLs
# ============================================================
def clean_image_url(url: str) -> str:
    """Normalize image URLs by removing resizing / CDN suffixes."""
    if not url:
        return url

    url = re.sub(r":[a-zA-Z]+(\?.*)?$", lambda m: m.group(1) if m.group(1) else "", url)
    url = re.sub(r"/\?w=\d+$", "", url)
    url = re.sub(r"\?w=\d+$", "", url)
    url = re.sub(r"\?format=\w+$", "", url)
    url = re.sub(r"(\.(jpg|jpeg|png|gif|webp|avif))/.*$", r"\1", url, flags=re.IGNORECASE)
    url = url.replace("https://https://", "https://")
    return url


# ============================================================
#  Extract all usable image URLs from gallery boxes
# ============================================================
async def extract_images_from_boxes(boxes):
    urls = set()

    for box in boxes:
        img = await box.query_selector("img")
        if not img:
            continue

        src = await img.get_attribute("src")
        if not src:
            continue

        src = clean_image_url(src)

        # Skip decorative / UI assets
        if any(skip in src.lower() for skip in ["logo", "blank.gif", "placeholder", "icon-play.svg"]):
            continue

        # Fix protocol-relative (//domain.com/image.jpg)
        if src.startswith("//"):
            src = "https:" + src

        # Fix site-relative (/wp-content/...jpg)
        elif not src.startswith("http"):
            src = urljoin(BASE_DOMAIN, src)

        # Ensure valid image ending
        if re.search(r"\.(jpg|jpeg|png|gif|webp|avif)([/?#:].*|$)", src, re.IGNORECASE) or "wp.com/" in src:
            urls.add(src)

    return list(urls)


# ============================================================
#  Main image processing entry
# ============================================================
async def process_images(
    boxes,
    out_dir,
    gallery_name=None,
    concurrency=4,
):
    """
    Extract image URLs → download them → return count.
    """
    urls = await extract_images_from_boxes(boxes)
    if not urls:
        return 0

    total = len(urls)
    sem = asyncio.Semaphore(concurrency)

    pbar = tqdm(
        total=total,
        desc=f"🖼️ {gallery_name}"[:20].ljust(20),
        ncols=66,
        leave=False,
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} 🖼️",
    )

    # ------------------------------------------------------------
    # Download single image
    # ------------------------------------------------------------
    async def download_one(url, idx):
        async with sem:
            try:
                ok = await asyncio.to_thread(
                    download_file,
                    url,
                    out_dir,
                    None,        # referer
                    None,        # force_ext
                    idx,         # index-number
                    gallery_name # prefix
                )
                pbar.update(1)
                return ok
            except:
                pbar.update(1)
                return False

    # ------------------------------------------------------------
    # Dispatch downloads
    # ------------------------------------------------------------
    results = await asyncio.gather(
        *(download_one(url, i + 1) for i, url in enumerate(urls)),
        return_exceptions=True
    )

    pbar.close()

    success = sum(1 for r in results if r is True)
    safe_print(f"🖼️ {gallery_name:<44}| {success}/{total} images")

    return success
