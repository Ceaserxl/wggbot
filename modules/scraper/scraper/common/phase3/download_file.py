# ============================================================
#  download_file.py — Phase 3 Low-level File Downloader
#  Location: scraper/common/phase3/download_file.py
# ============================================================

import os
import re
import time
import hashlib
import itertools
import requests
from urllib.parse import urlparse, unquote
from tqdm import tqdm

from scraper.common.common import HEADERS


# ============================================================
#  Sanitize WP/CDN image URLs
# ============================================================
def sanitize_image_url(url: str) -> str:
    """Normalize wp.com / CDN URLs by removing scaling suffixes."""
    if not url:
        return url

    url = re.sub(r":[a-zA-Z]+(\?.*)?$", lambda m: m.group(1) or "", url)
    url = re.sub(r"\?w=\d+$", "", url)
    return url


# ============================================================
#  Main File Downloader
# ============================================================
def download_file(
    url: str,
    folder: str,
    referer: str | None = None,
    force_ext: str | None = None,
    idx: int | None = None,
    gallery_name: str | None = None,
    debug: bool = True,
) -> bool:
    """
    Downloads images & videos with safe naming, resumable chunks,
    and silent skip for 403/404 responses.
    """
    url = sanitize_image_url(url)
    os.makedirs(folder, exist_ok=True)

    # ----------------------------------------------
    # Build safe filename
    # ----------------------------------------------
    parsed = urlparse(url)
    fname = os.path.basename(unquote(parsed.path)).split("?")[0].split("#")[0]

    # Fallback name
    if not fname or "." not in fname:
        hashed = hashlib.md5(url.encode()).hexdigest()[:10]
        if force_ext:
            fname = hashed + force_ext
        elif ".mp4" in url:
            fname = hashed + ".mp4"
        else:
            fname = hashed + ".jpg"

    ext = os.path.splitext(fname)[1]

    # Use gallery naming pattern
    if gallery_name and idx is not None:
        fname = f"{gallery_name}-{idx}{ext}"

    path = os.path.join(folder, fname)

    # Avoid overwriting
    if os.path.exists(path):
        base, ext2 = os.path.splitext(path)
        counter = itertools.count(2)
        while os.path.exists(path):
            path = f"{base}({next(counter)}){ext2}"

    # ----------------------------------------------
    # Request headers
    # ----------------------------------------------
    headers = HEADERS.copy()
    if referer:
        headers["Referer"] = referer

    CHUNK_SIZE = 1 * 1024 * 1024    # 1 MB
    FLUSH_EVERY = 512 * 1024 * 1024
    REQUEST_TIMEOUT = (10, 180)

    # ----------------------------------------------
    # Retry wrapper
    # ----------------------------------------------
    def attempt(retry=False) -> bool:
        try:
            tmp = f"{path}.part"
            resume = 0

            req_headers = HEADERS.copy()
            if referer:
                req_headers["Referer"] = referer

            # Resume support
            if os.path.exists(tmp):
                resume = os.path.getsize(tmp)
                if resume > 0:
                    req_headers["Range"] = f"bytes={resume}-"

            with requests.get(url, headers=req_headers, stream=True, timeout=REQUEST_TIMEOUT) as r:
                if r.status_code in (400, 403, 404):
                    return False

                # OK
                if r.status_code in (200, 206):
                    mode = "ab" if r.status_code == 206 and resume > 0 else "wb"
                    written = 0

                    with open(tmp, mode) as f:
                        for chunk in r.iter_content(CHUNK_SIZE):
                            if not chunk:
                                continue
                            f.write(chunk)
                            written += len(chunk)

                            if written >= FLUSH_EVERY:
                                f.flush()
                                os.fsync(f.fileno())
                                written = 0

                    os.replace(tmp, path)
                    return True

                # Server hiccup
                if r.status_code == 500:
                    time.sleep(1)
                    return attempt(True)

                if debug:
                    tqdm.write(f"⚠️ Unexpected status {r.status_code} for {fname}")
                return False

        except Exception as e:
            msg = str(e)

            # Handle partial reads
            if "IncompleteRead" in msg or "Connection broken" in msg:
                time.sleep(1)
                return attempt(True)

            # Common transient network issues
            if any(x in msg for x in ["403", "404", "Read timed out", "Max retries"]):
                return False

            if debug:
                tqdm.write(f"⚠️ Error downloading {fname}: {e}")

            return False

    # ----------------------------------------------
    # Final attempt + retry for images
    # ----------------------------------------------
    success = attempt()

    IMAGE_RETRY_COUNT = 3

    if not success and gallery_name == "image":
        for _ in range(IMAGE_RETRY_COUNT):
            time.sleep(1)
            if attempt(True):
                break

    return success
