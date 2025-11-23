# ============================================================
#  download_file.py — Robust Downloader (Images + Videos)
#  - Resume support
#  - Finite retries
#  - DNS-safe retry logic
#  - Correct extension detection
#  - Image/video fallback extensions
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
#  URL Sanitizer
# ============================================================
def sanitize_image_url(url: str) -> str:
    if not url:
        return url

    url = re.sub(r":[a-zA-Z]+(\?.*)?$", lambda m: m.group(1) or "", url)
    url = re.sub(r"\?w=\d+$", "", url)
    return url


# ============================================================
#  Extension Detection
# ============================================================
def detect_real_extension(path: str) -> str:
    kind = filetype.guess(path)
    if not kind:
        return None  # Let main logic decide fallback
    return f".{kind.extension}"


# ============================================================
#  MAIN DOWNLOADER
# ============================================================
def download_file(
    url: str,
    folder: str,
    referer: str | None = None,
    force_ext: str | None = None,
    idx: int | None = None,
    gallery_name: str | None = None,
    debug: bool = False,
) -> bool:

    url = sanitize_image_url(url)
    os.makedirs(folder, exist_ok=True)

    # Build base name
    parsed = urlparse(url)
    fname_raw = os.path.basename(unquote(parsed.path)).split("?")[0].split("#")[0]

    if not fname_raw or "." not in fname_raw:
        fname_raw = hashlib.md5(url.encode()).hexdigest()[:12]

    # tmp filename
    if gallery_name and idx is not None:
        tmp_name = f"{gallery_name}-{idx}.tmp"
    else:
        tmp_name = fname_raw + ".tmp"

    tmp_path = os.path.join(folder, tmp_name)

    # ----------------------------
    # Headers and config
    # ----------------------------
    headers = HEADERS.copy()
    if referer:
        headers["Referer"] = referer
    headers["Accept"] = "*/*"

    CHUNK_SIZE = 256 * 1024
    REQUEST_TIMEOUT = (10, 180)

    # Retry rules
    MAX_IMAGE_RETRIES = 10
    MAX_VIDEO_RETRIES = 10
    MAX_DNS_FAIL = 10

    attempts = 0
    dns_failures = 0

    url_lower = url.lower()
    VIDEO_EXTS = (".mp4", ".webm", ".mov", ".mkv", ".avi")

    # Determine if video
    is_video = any(url_lower.endswith(ext) for ext in VIDEO_EXTS)
    max_attempts = MAX_VIDEO_RETRIES if is_video else MAX_IMAGE_RETRIES

    # ============================================================
    #  RETRY LOOP
    # ============================================================
    while True:

        if attempts >= max_attempts:
            if debug:
                tqdm.write(f"❌ Retry limit reached ({attempts}/{max_attempts}) → skipping {url}")
            return False

        attempts += 1

        try:
            # Resume position
            resume_pos = os.path.getsize(tmp_path) if os.path.exists(tmp_path) else 0

            range_header = {}
            if resume_pos > 0:
                range_header["Range"] = f"bytes={resume_pos}-"

            req_headers = headers.copy()
            req_headers.update(range_header)

            # Perform request
            with requests.get(
                url,
                headers=req_headers,
                stream=True,
                timeout=REQUEST_TIMEOUT
            ) as r:

                # Permanent failure
                if r.status_code in (400, 403, 404, 410, 472):
                    if debug:
                        tqdm.write(f"❌ HTTP {r.status_code} (fatal) {url}")
                    return False

                # Only 200 (fresh) or 206 (resume) allowed
                if r.status_code not in (200, 206):
                    if debug:
                        tqdm.write(f"⚠️ HTTP {r.status_code} → retry ({attempts}/{max_attempts})")
                    time.sleep(1)
                    continue

                mode = "ab" if resume_pos > 0 else "wb"

                with open(tmp_path, mode) as f:
                    for chunk in r.iter_content(CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)

            # Success
            break

        except Exception as e:
            msg = str(e)

            # DNS failures
            if (
                "NameResolutionError" in msg
                or "Temporary failure in name resolution" in msg
                or "gaierror" in msg
            ):
                dns_failures += 1
                if debug:
                    tqdm.write(f"🌐 DNS fail {dns_failures}/{MAX_DNS_FAIL} {url}")

                if dns_failures >= MAX_DNS_FAIL:
                    if debug:
                        tqdm.write("❌ Too many DNS failures → skipping file")
                    return False

                time.sleep(2)
                continue

            # Generic retry
            if debug:
                tqdm.write(f"⚠️ Error {e} → retrying ({attempts}/{max_attempts})")

            time.sleep(1)
            continue

    # ============================================================
    #  EXTENSION HANDLING — FIX FOR IMAGES / VIDEOS
    # ============================================================

    # Preferred video fallback
    fallback_video_ext = ".mp4"

    # Attempt detection
    detected = detect_real_extension(tmp_path)

    # Choose final extension
    if force_ext:
        ext = force_ext

    elif is_video:
        # If detected invalid or image-like → fallback
        if detected in (None, "", ".jpg", ".png", ".gif", ".webp", ".jpeg"):
            ext = fallback_video_ext
        else:
            ext = detected

    else:
        # Image: fallback to .jpg if detection fails
        ext = detected if detected else ".jpg"

    # ============================================================
    #  FINAL RENAME
    # ============================================================
    if gallery_name and idx is not None:
        final_name = f"{gallery_name}-{idx}{ext}"
    else:
        base = os.path.splitext(fname_raw)[0]
        final_name = f"{base}{ext}"

    final_path = os.path.join(folder, final_name)

    # Avoid collisions
    if os.path.exists(final_path):
        base, ext2 = os.path.splitext(final_path)
        for num in itertools.count(2):
            alt = f"{base}({num}){ext2}"
            if not os.path.exists(alt):
                final_path = alt
                break

    # Safe rename
    for _ in range(20):
        try:
            os.replace(tmp_path, final_path)
            break
        except PermissionError:
            time.sleep(0.01)

    return True
