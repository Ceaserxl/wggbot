# ============================================================
#  download_file.py — Phase 3 Low-level File Downloader
#  Adds MIME detection + correct extension renaming
# ============================================================

import os
import re
import time
import hashlib
import itertools
import requests
import filetype
from urllib.parse import urlparse, unquote
from tqdm import tqdm

from scraper.common.common import HEADERS


# ============================================================
#  Sanitize WP/CDN image URLs (kept minimal)
# ============================================================
def sanitize_image_url(url: str) -> str:
    """Normalize wp.com / CDN URLs by removing scaling junk."""
    if not url:
        return url

    # Remove :large / :orig suffixes
    url = re.sub(r":[a-zA-Z]+(\?.*)?$", lambda m: m.group(1) or "", url)

    # Remove ?w=200 cache scaling
    url = re.sub(r"\?w=\d+$", "", url)

    return url


# ============================================================
#  Detect extension using filetype (modern, reliable)
# ============================================================
def detect_real_extension(path: str) -> str:
    """
    Detect real file type from bytes using filetype.
    Returns like '.jpg', '.png', '.webp', '.mp4', etc.
    Falls back to .jpg if unknown.
    """
    kind = filetype.guess(path)
    if not kind:
        return ".jpg"   # fallback
    return f".{kind.extension}"


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

    url = sanitize_image_url(url)
    os.makedirs(folder, exist_ok=True)

    # ----------------------------------------------
    # Build safe filename (TEMPORARY — ext added later)
    # ----------------------------------------------
    parsed = urlparse(url)
    fname_raw = os.path.basename(unquote(parsed.path)).split("?")[0].split("#")[0]

    # URL had no real filename → generate hashed name
    if not fname_raw or "." not in fname_raw:
        hashed = hashlib.md5(url.encode()).hexdigest()[:12]
        fname_raw = hashed  # NO extension yet

    # TEMPORARY name
    if gallery_name and idx is not None:
        fname_tmp = f"{gallery_name}-{idx}.tmp"
    else:
        fname_tmp = fname_raw + ".tmp"

    tmp_path = os.path.join(folder, fname_tmp)

    # Avoid leftover tmp files
    if os.path.exists(tmp_path):
        os.remove(tmp_path)

    # ----------------------------------------------
    # Request headers
    # ----------------------------------------------
    headers = HEADERS.copy()
    if referer:
        headers["Referer"] = referer

    CHUNK_SIZE = 1 * 1024 * 1024
    REQUEST_TIMEOUT = (10, 180)

    # ----------------------------------------------
    # Download file → tmp_path
    # ----------------------------------------------
    try:
        with requests.get(url, headers=headers, stream=True, timeout=REQUEST_TIMEOUT) as r:
            if r.status_code in (400, 403, 404):
                return False

            if r.status_code not in (200, 206):
                if debug:
                    tqdm.write(f"⚠️ Unexpected status {r.status_code} for {url}")
                return False

            with open(tmp_path, "wb") as f:
                for chunk in r.iter_content(CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)

    except Exception as e:
        if debug:
            tqdm.write(f"⚠️ Error downloading {url}: {e}")
        return False

    # ============================================================
    #  MIME DETECTION + FINAL FILE NAMING
    # ============================================================
    if force_ext:
        ext = force_ext
    else:
        ext = detect_real_extension(tmp_path)

    # Final filename
    if gallery_name and idx is not None:
        final_name = f"{gallery_name}-{idx}{ext}"
    else:
        base_name = os.path.splitext(fname_raw)[0]
        final_name = f"{base_name}{ext}"

    final_path = os.path.join(folder, final_name)

    # Ensure non-overwrite
    if os.path.exists(final_path):
        base, ext2 = os.path.splitext(final_path)
        counter = itertools.count(2)
        while os.path.exists(final_path):
            final_path = f"{base}({next(counter)}){ext2}"

    # Rename tmp → final
    os.replace(tmp_path, final_path)

    return True
