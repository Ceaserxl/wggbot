# ============================================================
#  videos.py — Phase 2 Video Extraction + Download Dispatcher
#  Location: scraper/common/phase2/videos.py
# ============================================================

import os
import re
import base64
import asyncio
from urllib.parse import urlparse, parse_qs
from tqdm import tqdm

# -----------------------------
# Project imports (correct)
# -----------------------------
from scraper.common.common import (
    BASE_DOMAIN,
    decode_file_param,
    launch_chromium,
)
from scraper.common.phase3.download_file import download_file


# Pattern for valid video extensions
VIDEO_EXT_PATTERN = (
    r"\.(mp4|webm|mkv|mov|avi|flv|m4v|wmv|ts|mpeg|mpg)([/?#]|$)"
)


# ============================================================
#  Extract all video server URLs from the video page
# ============================================================
async def extract_video_servers(page):
    servers = []

    # ------------------------------------------------------------
    # 1) Button-based Base64 encoded "file=" parameters
    # ------------------------------------------------------------
    buttons = await page.query_selector_all("button.sv-change")
    for btn in buttons:
        val = await btn.get_attribute("value")
        if not val:
            continue

        try:
            decoded = base64.b64decode(val).decode(errors="ignore")
            qs = parse_qs(urlparse(decoded).query)
            if "file" in qs:
                real = decode_file_param(qs["file"][0])
                if real:
                    servers.append(real)
        except:
            continue

    # ------------------------------------------------------------
    # 2) Raw HTML regex extraction of video URLs
    # ------------------------------------------------------------
    html = await page.content()

    # Regex may return either raw string OR tuple depending on groups
    found = re.findall(r"(https?://[^\s\"']+" + VIDEO_EXT_PATTERN + ")", html, re.IGNORECASE)

    for item in found:
        if isinstance(item, tuple):
            servers.append(item[0])
        else:
            servers.append(item)

    return servers


# ============================================================
#  Resolve dood / embed links → real video URL
# ============================================================
async def resolve_dood_link(context, url):
    try:
        page = await context.new_page()
        page.set_default_timeout(15000)

        try:
            await page.goto(url, timeout=15000)
        except:
            await page.close()
            return None

        # Try <video> and <source> tags
        resolved = (
            await page.get_attribute("video", "src")
            or await page.get_attribute("source", "src")
        )

        # Fallback regex
        if not resolved:
            html = await page.content()
            m = re.search(r"https?://[^\s\"']+" + VIDEO_EXT_PATTERN, html)
            if m:
                resolved = m.group(0)

        await page.close()
        return resolved

    except:
        return None


# ============================================================
#  Threaded file download wrapper
# ============================================================
async def download_video_task(url, out_dir, gallery_name, idx):
    """
    Wrap synchronous download_file() into asyncio using a thread.
    """
    try:
        ok = await asyncio.to_thread(
            download_file,
            url,
            out_dir,
            None,            # referer
            None,            # force_ext
            idx,             # image/video index
            gallery_name,    # gallery prefix
        )
        return ok
    except:
        return False


# ============================================================
#  MAIN VIDEO PROCESSOR
# ============================================================
async def process_videos(boxes, out_dir, gallery_name=None, concurrency=4, context=None):
    """
    Extract + download videos.
    Indexing is based ONLY on actual video boxes, not image boxes.
    """

    # ------------------------------------------------------------------
    # 1) Detect already-downloaded files
    # ------------------------------------------------------------------
    existing = set()
    for f in os.listdir(out_dir):
        if f.startswith(f"{gallery_name}-"):
            idx_part = f.split("-")[-1].split(".")[0]
            if idx_part.isdigit():
                existing.add(int(idx_part))

    # ------------------------------------------------------------------
    # 2) Filter only boxes with play icon
    # ------------------------------------------------------------------
    video_boxes = []
    for b in boxes:
        if await b.query_selector("img[src*='icon-play.svg']"):
            video_boxes.append(b)

    total = len(video_boxes)
    if total == 0:
        return 0

    # ------------------------------------------------------------------
    # 3) Setup concurrency + state
    # ------------------------------------------------------------------
    seen_urls = set()
    success_count = 0
    sem = asyncio.Semaphore(concurrency)

    pbar = tqdm(
        total=total,
        desc=f"🎞️ {gallery_name}"[:20].ljust(20),
        ncols=66,
        leave=False,
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} 🎞️",
    )

    # ------------------------------------------------------------------
    # 4) Correct per-video index (1..N in filtered list)
    # ------------------------------------------------------------------
    async def handle(video_index, box):
        nonlocal success_count

        # Skip existing
        if video_index in existing:
            pbar.update(1)
            return True

        async with sem:
            try:
                # Find <a> tag containing play icon
                a = await box.query_selector("a:has(img[src*='icon-play.svg'])")
                if not a:
                    pbar.update(1)
                    return False

                href = await a.get_attribute("href")
                if not href:
                    pbar.update(1)
                    return False

                # Full video page URL
                video_page = BASE_DOMAIN + href if href.startswith("/") else href

                # Open page
                vpage = await context.new_page()
                try:
                    await vpage.goto(video_page, timeout=30000)
                    servers = await extract_video_servers(vpage)
                finally:
                    await vpage.close()

                if not servers:
                    pbar.update(1)
                    return False

                # ==========================================================
                # Try every server until one works
                # ==========================================================
                for server in servers:
                    if server in seen_urls:
                        continue
                    seen_urls.add(server)

                    # Direct video file
                    if re.search(VIDEO_EXT_PATTERN, server, re.IGNORECASE):
                        ok = await download_video_task(
                            server, out_dir, gallery_name, video_index
                        )
                        if ok:
                            success_count += 1
                            pbar.update(1)
                            return True

                    # Embed-style server
                    if any(x in server for x in ["dood.", "embed-", "bigwarp.io", "/embed/"]):
                        resolved = await resolve_dood_link(context, server)
                        if resolved and re.search(VIDEO_EXT_PATTERN, resolved, re.IGNORECASE):
                            ok = await download_video_task(
                                resolved, out_dir, gallery_name, video_index
                            )
                            if ok:
                                success_count += 1
                                pbar.update(1)
                                return True

            except:
                pbar.update(1)
                return False

            pbar.update(1)
            return False

    # ------------------------------------------------------------------
    # 5) Run all downloads
    # ------------------------------------------------------------------
    await asyncio.gather(
        *(handle(i, box) for i, box in enumerate(video_boxes, start=1))
    )

    pbar.close()
    tqdm.write(f"🎞️ {gallery_name:<46}| {success_count}/{total} videos 🎞️")
    return success_count
