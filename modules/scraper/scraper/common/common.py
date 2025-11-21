import os
import re
import time
import base64
import hashlib
import itertools
import requests
import asyncio
from urllib.parse import urlparse, unquote, parse_qs
from bs4 import BeautifulSoup
from tqdm import tqdm
import os, time, hashlib, itertools, requests
from urllib.parse import urlparse, unquote

# ============================================================
#  Global Configuration
# ============================================================
BASE_DOMAIN = "https://thefap.net"
ROOT_DIR = "downloads"
HEADERS = {"User-Agent": "Mozilla/5.0 (CeaserXL-Async/1.0)"}

# ============================================================
#  URL Sanitization
# ============================================================
def sanitize_image_url(url: str) -> str:
    """
    Clean up image URLs served via i0.wp.com and similar CDNs.
    Removes scaling tokens like ':small?w=600' or '?w=1200'.
    """
    # Remove trailing size modifiers
    url = re.sub(r":[a-z]+(\?.*)?$", lambda m: m.group(1) if m.group(1) else "", url)
    # Remove ?w= params and cleanup stray artifacts
    url = re.sub(r"\?w=\d+$", "", url)
    return url

# ============================================================
#  File Download (Sync)
# ============================================================
def download_file(
    url,
    folder,
    referer=None,
    force_ext=None,
    idx=None,
    gallery_name=None,
    debug=True,  # ✅ toggle for showing/hiding non-404/403 errors
):
    """
    Download a file (image or video) with safe naming, retry handling, and tqdm-safe logging.
    Skips visible output for HTTP 404 / 403 errors.
    """
    url = sanitize_image_url(url)
    os.makedirs(folder, exist_ok=True)

    parsed = urlparse(url)
    fname = os.path.basename(unquote(parsed.path)).split("?")[0].split("#")[0]

    # Fallback name generation
    if not fname or "." not in fname:
        if force_ext:
            fname = hashlib.md5(url.encode()).hexdigest()[:10] + force_ext
        elif ".mp4" in url:
            fname = hashlib.md5(url.encode()).hexdigest()[:10] + ".mp4"
        else:
            fname = hashlib.md5(url.encode()).hexdigest()[:10] + ".jpg"

    ext = os.path.splitext(fname)[1]

    # Custom naming pattern: <gallery>-<index>.<ext>
    if gallery_name and idx is not None:
        fname = f"{gallery_name}-{idx}{ext}"

    # Avoid overwriting existing files
    path = os.path.join(folder, fname)
    if os.path.exists(path):
        base, ext = os.path.splitext(path)
        counter = itertools.count(2)
        while os.path.exists(path):
            path = f"{base}({next(counter)}){ext}"

    headers = HEADERS.copy()
    if referer:
        headers["Referer"] = referer

    IMAGE_RETRY_COUNT = 3
    MEGABYTES = 1 # 1 MB chunks (remote-optimized)
    CHUNK_SIZE = MEGABYTES * 1024 * 1024  
    FLUSH_EVERY = 512 * 1024 * 1024 # flush every ~0.5 GB
    REQUEST_TIMEOUT = (10, 180)

    def attempt_download(retry=False):
        try:
            tmp_path = f"{path}.part"
            resume_pos = 0

            # Build fresh headers each try to avoid sticky Range
            req_headers = HEADERS.copy()
            if referer:
                req_headers["Referer"] = referer

            if os.path.exists(tmp_path):
                resume_pos = os.path.getsize(tmp_path)
                if resume_pos > 0:
                    req_headers["Range"] = f"bytes={resume_pos}-"

            with requests.get(url, headers=req_headers, stream=True, timeout=REQUEST_TIMEOUT) as r:
                # skip common dead links silently
                if r.status_code in (403, 404, 400):
                    return False

                if r.status_code in (200, 206):
                    mode = "ab" if r.status_code == 206 and resume_pos > 0 else "wb"
                    written = 0

                    # 1 MB chunks for remote stability
                    with open(tmp_path, mode) as f:
                        for chunk in r.iter_content(CHUNK_SIZE):
                            if not chunk:
                                continue
                            f.write(chunk)
                            written += len(chunk)
                            if written >= FLUSH_EVERY:  
                                f.flush()
                                os.fsync(f.fileno())
                                written = 0

                    os.replace(tmp_path, path)
                    #tqdm.write(f"      ✅ Saved: {gallery_name}-{idx}{ext}.")
                    return True
                else:
                    if r.status_code == 500:
                        # wait and retry once, server hiccup
                        time.sleep(1)
                        return attempt_download(retry=True)
                    if debug:
                        tqdm.write(f"      ⚠️  Unexpected status {r.status_code} for {gallery_name}-{idx}{ext}")
                    return False

        except Exception as e:
            msg = str(e)
            # allow resume on partial/incomplete
            if "IncompleteRead" in msg or "Connection broken" in msg:
                tqdm.write(f"      ⚠️  Partial download detected — resuming {gallery_name}-{idx}{ext}...")
                time.sleep(1)
                return attempt_download(retry=True)
            # suppress common transient codes
            if any(x in msg for x in ["403", "404", "500", "Read timed out", "Max retries exceeded"]):
                return False
            if debug:
                tqdm.write(f"      ⚠️  Download error ({gallery_name}-{idx}{ext}): {e}")
            return False

    success = attempt_download()

    # Retry logic (only for images)
    if not success and gallery_name == "image":
        for attempt in range(IMAGE_RETRY_COUNT):
            time.sleep(1)
            success = attempt_download(retry=True)
            if success:
                break

    if not success:
        #if debug:
            #tqdm.write(f"      ❌ Failed: {gallery_name}-{idx}{ext}.")
        return False

    return True

# ============================================================
#  Video Helpers
# ============================================================
def decode_file_param(file_val: str) -> str | None:
    """Decode base64 or plain URLs from 'file' parameters."""
    if not file_val:
        return None
    if file_val.startswith("http"):
        return file_val
    try:
        decoded = base64.b64decode(file_val).decode(errors="ignore")
        if decoded.startswith("http"):
            return decoded
    except Exception:
        pass
    return None

# ============================================================
#  Search Helpers (optional)
# ============================================================
def get_search_results(term):
    """
    Scrape all gallery links from paginated search results.
    Used only for manual lookup — not called during async scraping.
    """
    results = set()
    page = 1
    while True:
        url = f"{BASE_DOMAIN}/search/{term}/{page}/"
        print(f"🔎 Searching page {page}: {url}")
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                break
        except Exception as e:
            print(f"    ❌ Request failed on page {page}.")
            break

        soup = BeautifulSoup(r.text, "html.parser")
        links = [
            BASE_DOMAIN + a["href"]
            for a in soup.select("a[href^='/']")
            if re.search(r"-\d+/?$", a["href"])
        ]
        before = len(results)
        results.update(links)
        if len(results) == before:
            break
        page += 1

    print(f"✅ {len(results)} galleries found for term: {term}")
    return list(results)

# ============================================================
#  Miscellaneous Utilities
# ============================================================
def get_gallery_media_count(page):
    """Extract numeric media count from gallery page text."""
    try:
        text = page.inner_text("body")
        match = re.search(r"(\d+)\s+media", text, re.IGNORECASE)
        return int(match.group(1)) if match else None
    except Exception:
        return None

# ============================================================
#  Playwright Helper — Unified GPU-Accelerated Chromium Launch
# ============================================================
from playwright.async_api import async_playwright

async def launch_chromium(user_data_dir: str | None = None, headless: bool = True):
    """
    Launch a GPU-accelerated Chromium browser in *incognito* mode.
    We ignore user_data_dir and do NOT use a persistent profile to avoid
    massive disk usage and speed up startup.
    Returns:
        (playwright, context)
    """
    gpu_args = [
        "--enable-gpu",
        "--ignore-gpu-blocklist",
        "--use-gl=desktop",
        "--enable-gpu-rasterization",
        "--enable-zero-copy",
        "--enable-accelerated-video-decode",
        "--enable-accelerated-jpeg-decoding",
        "--enable-accelerated-webp-decoding",
        "--enable-native-gpu-memory-buffers",
        "--force-gpu-mem-available-mb=16384",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-client-side-phishing-detection",
        "--disable-default-apps",
        "--disable-sync",
        "--no-first-run",
        "--disable-crash-reporter",
        "--disable-hang-monitor",
        "--disable-popup-blocking",
        "--disable-translate",
        "--ignore-certificate-errors",
    ]

    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=headless, args=gpu_args)
    context = await browser.new_context()
    return p, context