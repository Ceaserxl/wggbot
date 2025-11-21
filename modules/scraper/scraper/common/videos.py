import os
import re
import base64
import asyncio
from urllib.parse import urlparse, parse_qs
from tqdm import tqdm
from .common import BASE_DOMAIN, decode_file_param, download_file, launch_chromium


# ============================================================
#  Video Extraction & Resolution Helpers
# ============================================================

VIDEO_EXT_PATTERN = r"\.(mp4|webm|mkv|mov|avi|flv|m4v|wmv|ts|mpeg|mpg)([/?#]|$)"


async def extract_video_servers(page):
    """Extract all potential playable video URLs from a video page."""
    servers = []

    # Extract from Base64-encoded buttons
    buttons = await page.query_selector_all("button.sv-change")
    for btn in buttons:
        val = await btn.get_attribute("value")
        if not val:
            continue
        try:
            decoded = base64.b64decode(val).decode(errors="ignore")
            qs = parse_qs(urlparse(decoded).query)
            if "file" in qs:
                real_url = decode_file_param(qs["file"][0])
                if real_url:
                    servers.append(real_url)
        except Exception:
            continue

    # Extract from raw HTML (direct video links)
    html = await page.content()
    for m in re.findall(r"https?://[^\s\"']+" + VIDEO_EXT_PATTERN, html, re.IGNORECASE):
        # m is a tuple due to the grouped regex; join only the first part
        if isinstance(m, tuple):
            servers.append(m[0])
        else:
            servers.append(m)

    return servers


async def resolve_dood_link(context, dood_url: str) -> str | None:
    """Resolve dood/embed URLs into playable video links."""
    resolved_url = None
    try:
        page = await context.new_page()
        page.set_default_timeout(15000)
        try:
            await page.goto(dood_url, timeout=15000)
        except Exception:
            await page.close()
            return None

        resolved_url = (
            await page.get_attribute("video", "src")
            or await page.get_attribute("source", "src")
        )

        if not resolved_url:
            html = await page.content()
            match = re.search(r"https?://[^\s\"']+" + VIDEO_EXT_PATTERN, html)
            if match:
                resolved_url = match.group(0)

        await page.close()
    except Exception:
        pass

    return resolved_url


# ============================================================
#  Download Management
# ============================================================

async def download_video_task(url, out_dir, gallery_name, idx):
    """Download a single video file."""
    try:
        ok = await asyncio.to_thread(
            download_file, url, out_dir, None, None, idx, "video"
        )
        await asyncio.sleep(0.05)
        return ok
    except Exception:
        return False

# ============================================================
#  Main Video Processing Logic
# ============================================================
async def process_videos(boxes, out_dir, gallery_name=None, concurrency=5, context=None):
    """Extract video links from gallery boxes and download them concurrently."""
    total_videos = len(boxes)
    if total_videos == 0:
        return 0

    success_count = 0
    seen = set()
    sem = asyncio.Semaphore(concurrency)
    
    pbar = tqdm(
        total=total_videos,
        desc=f"🎞️ {gallery_name}"[:20].ljust(20),
        ncols=66,
        position=0,
        leave=False,
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} 🎞️"
    )

    async def handle_box(idx, box):
        nonlocal success_count
        async with sem:
            try:
                # Find the <a> that wraps the play icon
                a = await box.query_selector("a:has(img[src*='icon-play.svg'])")
                if not a:
                    return False

                href = await a.get_attribute("href")
                if not href:
                    return False

                vid_page_url = BASE_DOMAIN + href if href.startswith("/") else href

                # Use the shared context from main.py (per-gallery)
                vpage = await context.new_page()
                try:
                    await vpage.goto(vid_page_url, timeout=30000)
                    servers = await extract_video_servers(vpage)
                finally:
                    await vpage.close()

                if not servers:
                    return False

                for server in servers:
                    if server in seen:
                        continue
                    seen.add(server)

                    ok = False
                    # Direct playable link
                    if re.search(VIDEO_EXT_PATTERN, server, re.IGNORECASE):
                        ok = await download_video_task(server, out_dir, gallery_name, idx)
                    # Dood/embed style links
                    elif any(x in server for x in ["dood.", "embed-", "bigwarp.io", "/embed/"]):
                        resolved = await resolve_dood_link(context, server)
                        if resolved and re.search(VIDEO_EXT_PATTERN, resolved, re.IGNORECASE):
                            ok = await download_video_task(resolved, out_dir, gallery_name, idx)

                    if ok:
                        success_count += 1
                        pbar.update(1)
                        return True

            except Exception:
                return False

            return False  # nothing succeeded

    results = await asyncio.gather(*(handle_box(i, b) for i, b in enumerate(boxes, start=1)))
    pbar.close()

    success = sum(1 for r in results if r)
    tqdm.write(f"🎞️ {gallery_name:<46}| {f'{success}/{total_videos} videos 🎞️':>15}")
    return success

