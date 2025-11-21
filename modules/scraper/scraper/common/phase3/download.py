# ============================================================
#  download.py — Phase 3 (Images + Videos)
# ============================================================

import os
from urllib.parse import urlparse
from tqdm import tqdm
import asyncio

from scraper.common.common import print_banner, launch_chromium, safe_print
import scraper.common.settings as settings

from scraper.common.phase3.download_file import download_file
from scraper.common.phase3.video_resolver import resolve_video_page

# DB media fetchers
from scraper.common.phase3.get_media_db import (
    get_gallery_images,
    get_gallery_video_pages
)


# ============================================================
#  IMAGES
# ============================================================
async def download_images(img_urls, img_dir, gallery_name):
    semaphore = asyncio.Semaphore(settings.IMG_CONC)
    total = len(img_urls)
    success = 0

    pbar = tqdm(
        total=total,
        desc=f"🖼️ {gallery_name}"[:20].ljust(20),
        ncols=66,
        leave=False,
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} 🖼️"
    )

    async def task(url, idx):
        nonlocal success
        async with semaphore:
            ok = await asyncio.to_thread(
                download_file, url, img_dir, None, None, idx, gallery_name
            )
            if ok:
                success += 1
            pbar.update(1)

    await asyncio.gather(*(task(url, i + 1) for i, url in enumerate(img_urls)))

    pbar.close()
    safe_print(f"🖼️ {gallery_name:<44}| {success}/{total} images")
    return success


# ============================================================
#  VIDEOS
# ============================================================
async def download_videos(video_pages, vid_dir, gallery_name):
    total = len(video_pages)
    if total == 0:
        return 0

    # Launch single browser
    p, context = await launch_chromium(f"userdata/video_{gallery_name}", headless=True)

    semaphore = asyncio.Semaphore(settings.VID_CONC)
    success = 0

    pbar = tqdm(
        total=total,
        desc=f"🎞️ {gallery_name}"[:20].ljust(20),
        ncols=66,
        leave=False,
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} 🎞️"
    )

    async def task(video_page, idx):
        nonlocal success
        async with semaphore:
            real = await resolve_video_page(context, video_page)
            if real:
                ok = await asyncio.to_thread(
                    download_file, real, vid_dir, None, None, idx, gallery_name
                )
                if ok:
                    success += 1
            pbar.update(1)

    await asyncio.gather(*(task(page, i + 1) for i, page in enumerate(video_pages)))

    pbar.close()
    safe_print(f"🎞️ {gallery_name:<44}| {success}/{total} videos")

    await context.close()
    await p.stop()
    return success


# ============================================================
#  MASTER PHASE 3
# ============================================================
async def phase3_download(ordered_galleries, interwoven=False):
    print_banner("Phase 3 — Downloading", "🚀")

    stats = {}  # tag → { gallery → [img_count, vid_count] }

    def ensure(tag, gallery):
        if tag not in stats:
            stats[tag] = {}
        if gallery not in stats[tag]:
            stats[tag][gallery] = [0, 0]

    # ============================================================
    #  PHASE 3A — IMAGES
    # ============================================================
    print_banner("Phase 3A — Images", "🖼️")

    with tqdm(total=len(ordered_galleries), desc="🖼️ Images", ncols=66) as bar:
        for link, tag, _snips, _box_count, _tag_total in ordered_galleries:

            gallery_name = os.path.basename(urlparse(link).path.strip("/"))
            ensure(tag, gallery_name)

            # NEW FOLDER SCHEME:
            # downloads/<tag>/<gallery>/images/
            root = settings.download_path
            gallery_root = os.path.join(root, tag, gallery_name)
            img_dir = os.path.join(gallery_root, "images")

            # Get image URLs from DB
            image_urls = await get_gallery_images(link)

            # Download images
            img_count = await download_images(image_urls, img_dir, gallery_name)
            stats[tag][gallery_name][0] = img_count

            bar.update(1)

"""     # ============================================================
    #  PHASE 3B — VIDEOS
    # ============================================================
    print_banner("Phase 3B — Videos", "🎞️")

    with tqdm(total=len(ordered_galleries), desc="🎞️ Videos", ncols=66) as bar:
        for link, tag, _snips, _box_count, _tag_total in ordered_galleries:

            gallery_name = os.path.basename(urlparse(link).path.strip("/"))
            ensure(tag, gallery_name)

            # NEW FOLDER SCHEME:
            # downloads/<tag>/<gallery>/videos/
            root = settings.download_path
            gallery_root = os.path.join(root, tag, gallery_name)
            vid_dir = os.path.join(gallery_root, "videos")

            # Get video page URLs from DB
            video_pages = await get_gallery_video_pages(link)

            # Download videos
            vid_count = await download_videos(video_pages, vid_dir, gallery_name)
            stats[tag][gallery_name][1] = vid_count

            bar.update(1)

    return stats """
