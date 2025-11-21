import os
import re
import base64
import asyncio
from urllib.parse import urlparse, parse_qs
from tqdm import tqdm
from .common import BASE_DOMAIN, decode_file_param, download_file, launch_chromium


VIDEO_EXT_PATTERN = r"\.(mp4|webm|mkv|mov|avi|flv|m4v|wmv|ts|mpeg|mpg)([/?#]|$)"


# ============================================================
#  VIDEO URL EXTRACTION
# ============================================================
async def extract_video_servers(page):
    servers = []

    # Buttons with Base64-encoded data
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
        except:
            continue

    # Raw HTML search
    html = await page.content()
    for m in re.findall(r"https?://[^\s\"']+" + VIDEO_EXT_PATTERN, html, re.IGNORECASE):
        servers.append(m[0] if isinstance(m, tuple) else m)

    return servers


async def resolve_dood_link(context, url):
    try:
        page = await context.new_page()
        page.set_default_timeout(15000)

        try:
            await page.goto(url, timeout=15000)
        except:
            await page.close()
            return None

        resolved = (
            await page.get_attribute("video", "src") or
            await page.get_attribute("source", "src")
        )

        if not resolved:
            html = await page.content()
            match = re.search(r"https?://[^\s\"']+" + VIDEO_EXT_PATTERN, html)
            if match:
                resolved = match.group(0)

        await page.close()
        return resolved
    except:
        return None


# ============================================================
#  FILE DOWNLOAD TASK
# ============================================================
async def download_video_task(url, out_dir, gallery_name, idx):
    """Download single video with correct naming."""
    try:
        ok = await asyncio.to_thread(
            download_file,
            url,
            out_dir,
            None,
            None,
            idx,
            gallery_name       # IMPORTANT FIX
        )
        return ok
    except:
        return False

# ============================================================
#  MAIN VIDEO PROCESSOR
# ============================================================
async def process_videos(boxes, out_dir, gallery_name=None, concurrency=4, context=None):
    """
    Process only boxes containing a play button.
    Index is based ONLY on real video boxes (1..N).
    """

    # ============================================================
    #   1. Detect existing downloaded videos
    # ============================================================
    existing = set()
    for f in os.listdir(out_dir):
        if f.startswith(f"{gallery_name}-"):
            idx_part = f.split("-")[-1].split(".")[0]
            if idx_part.isdigit():
                existing.add(int(idx_part))

    # ============================================================
    #   2. Filter boxes WITH play icon (correct video list)
    # ============================================================
    video_boxes = []
    for b in boxes:
        if await b.query_selector("img[src*='icon-play.svg']"):
            video_boxes.append(b)

    total = len(video_boxes)
    if total == 0:
        return 0

    # ============================================================
    #   3. Setup concurrency + tracking
    # ============================================================
    seen_urls = set()
    sem = asyncio.Semaphore(concurrency)
    success_count = 0

    pbar = tqdm(
        total=total,
        desc=f"🎞️ {gallery_name}"[:20].ljust(20),
        ncols=66,
        leave=False,
        position=0,
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} 🎞️"
    )

    # ============================================================
    #   4. Correct index = video_box index, not raw box index
    # ============================================================
    async def handle(video_index, box):
        nonlocal success_count

        # Skip already-downloaded index
        if video_index in existing:
            pbar.update(1)
            return True

        async with sem:
            try:
                # a-tag containing play icon
                a = await box.query_selector("a:has(img[src*='icon-play.svg'])")
                if not a:
                    pbar.update(1)
                    return False

                href = await a.get_attribute("href")
                if not href:
                    pbar.update(1)
                    return False

                # Build page URL
                video_page = BASE_DOMAIN + href if href.startswith("/") else href

                # Open video page
                vpage = await context.new_page()
                try:
                    await vpage.goto(video_page, timeout=30000)
                    servers = await extract_video_servers(vpage)
                finally:
                    await vpage.close()

                if not servers:
                    pbar.update(1)
                    return False

                # ====================================================
                #   Resolve servers until one downloads
                # ====================================================
                for server in servers:
                    if server in seen_urls:
                        continue
                    seen_urls.add(server)

                    # direct link
                    if re.search(VIDEO_EXT_PATTERN, server, re.IGNORECASE):
                        ok = await download_video_task(
                            server, out_dir, gallery_name, video_index
                        )
                        if ok:
                            success_count += 1
                            pbar.update(1)
                            return True

                    # dood / embed
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

            # nothing worked
            pbar.update(1)
            return False

    # ============================================================
    #   5. Launch downloads — index is based on filtered list
    # ============================================================
    await asyncio.gather(
        *(handle(i, box) for i, box in enumerate(video_boxes, start=1))
    )

    pbar.close()
    tqdm.write(f"🎞️ {gallery_name:<46}| {success_count}/{total} videos 🎞️")
    return success_count
