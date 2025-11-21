import re
import asyncio
import random
import threading
from urllib.parse import urljoin
from tqdm import tqdm
from .common import BASE_DOMAIN, download_file
from rich.console import Console
from io import StringIO

# ============================================================
#  Thread-safe printing
# ============================================================
console = Console(file=StringIO(), force_terminal=True, color_system="auto")
print_lock = threading.Lock()
def safe_print(*args, **kwargs):
    """Thread-safe print that supports Rich markup but preserves tqdm formatting."""
    with print_lock:
        # Render Rich markup into a string
        buf = StringIO()
        temp_console = Console(file=buf, force_terminal=True, color_system="auto")
        temp_console.print(*args, **kwargs)
        output = buf.getvalue().rstrip("\n")
        tqdm.write(output)

# ============================================================
#  Utility: Clean wp.com or scaled image URLs
# ============================================================

def clean_image_url(url: str) -> str:
    """Normalize image URLs by removing :small?w=600 or /?w=600 suffixes."""
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
#  Image Extraction from Boxes
# ============================================================

async def extract_images_from_boxes(boxes):
    """Extract <img src> URLs directly from gallery boxes."""
    urls = set()
    for box in boxes:
        img = await box.query_selector("img")
        if not img:
            continue

        src = await img.get_attribute("src")
        if not src:
            continue

        src = clean_image_url(src)

        # Skip decorative / placeholder images
        if any(skip in src.lower() for skip in ["logo", "blank.gif", "placeholder", "icon-play.svg"]):
            continue

        # Fix relative or protocol-less URLs
        if src.startswith("//"):
            src = "https:" + src
        elif not src.startswith("http"):
            src = urljoin(BASE_DOMAIN, src)

        if re.search(r"\.(jpg|jpeg|png|gif|webp|avif)([/?#:].*|$)", src, re.IGNORECASE) or "wp.com/" in src:
            urls.add(src)

    return list(urls)


# ============================================================
#  Image Processing Logic
# ============================================================
async def process_images(
    boxes,
    out_dir,
    gallery_name=None,
    concurrency=1,
):
    urls = await extract_images_from_boxes(boxes)
    if not urls:
        return 0

    total = len(urls)
    semaphore = asyncio.Semaphore(concurrency)

    pbar = tqdm(
        total=total,
        desc=f"🖼️ {gallery_name}"[:20].ljust(20),
        ncols=66,
        position=0,
        leave=False,
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} 🖼️"
    )

    async def download_one(url, idx):
        async with semaphore:
            try:
                ok = await asyncio.to_thread(
                    download_file,
                    url,
                    out_dir,
                    None,
                    None,
                    idx,
                    gallery_name     # <-- IMPORTANT FIX
                )
                pbar.update(1)
                return ok
            except Exception:
                tqdm.write(f"❌ image-{idx} download error.")
                return False

    tasks = [download_one(url, i + 1) for i, url in enumerate(urls)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    pbar.close()
    success = sum(1 for r in results if r is True)

    safe_print(f"🖼️ {gallery_name:<44}| {f'{success}/{total} images 🖼️':>17}")

    return success
