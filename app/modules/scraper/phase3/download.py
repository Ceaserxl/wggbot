# ============================================================
#  download.py — Phase 3 (Images + Videos) — S3 Integrated
# ============================================================

import os
import re
import asyncio
from urllib.parse import urlparse
from pathlib import Path
from tqdm import tqdm

from scraper.common.common import print_banner, launch_chromium, safe_print
import scraper.common.settings as settings

from .download_file import download_file
from .video_resolver import resolve_video_page

from ..common.s3 import (
    s3_has_image,
    s3_has_video,
    s3_restore_image,
    s3_restore_video,
    s3_upload_image,
    s3_upload_video,
)

# ============================================================
#  INTERWOVEN MODE
# ============================================================
INTERWOVEN = True


# ============================================================
#  DEBUG SETUP
# ============================================================
debug = False
PHASE3_DIR = Path(__file__).resolve().parent
PHASE3_DEBUG_FILE = PHASE3_DIR / "phase3_debug.txt"


def dlog(*args):
    if not debug:
        return
    try:
        with open(PHASE3_DEBUG_FILE, "a", encoding="utf-8") as f:
            f.write(" ".join(str(a) for a in args) + "\n")
    except:
        pass


def sanitize_gallery_name(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", name)


# ============================================================
#  FILE HELPERS
# ============================================================
def find_index_file(folder: str, gallery_name: str, idx: int) -> Path | None:
    prefix = f"{gallery_name}-{idx}"
    folder_path = Path(folder)

    if not folder_path.exists():
        return None

    for fname in os.listdir(folder_path):
        if fname.startswith(prefix) and not fname.endswith(".tmp"):
            return folder_path / fname

    return None


def index_file_exists(folder: str, gallery_name: str, idx: int) -> bool:
    return find_index_file(folder, gallery_name, idx) is not None


# ============================================================
#  MASTER PHASE 3 — IMAGES + VIDEOS (S3-based)
# ============================================================
async def phase3_download(
    ordered_galleries,
    p2a_results,
    p2b_results,
    interwoven=False,
):
    print_banner("Phase 3 — Downloading", "🚀")

    stats: dict[str, dict[str, list[int]]] = {}

    def ensure(tag, gallery):
        if tag not in stats:
            stats[tag] = {}
        if gallery not in stats[tag]:
            stats[tag][gallery] = [0, 0]  # [images, videos]

    gallery_conc = getattr(settings, "GALLERY_CONC", 2)
    img_conc = getattr(settings, "IMG_CONC", 10)
    vid_conc = getattr(settings, "VID_CONC", 5)

    sem_gallery = asyncio.Semaphore(gallery_conc)

    # ------------------------------------------------------------
    #  INTERNAL WORKERS (FULLY REUSED)
    # ------------------------------------------------------------
    async def process_gallery_images(link, tag, snippets):
        async with sem_gallery:
            raw_name = os.path.basename(urlparse(link).path.strip("/"))
            gallery_name = sanitize_gallery_name(raw_name)
            ensure(tag, gallery_name)

            root = settings.download_path
            img_dir = Path(root) / tag / gallery_name / "images"

            image_items = p2a_results.get(link, [])
            total_imgs = len(image_items)
            img_count = 0

            gallery_pbar = tqdm(
                total=total_imgs,
                desc=f"🖼️ {gallery_name}"[:20].ljust(20),
                ncols=66,
                leave=False,
                position=0,
                bar_format="{l_bar}{bar}|{n_fmt:>3}/{total_fmt} images 🖼️",
            )

            missing = []

            # ----- PREPASS -----
            for idx, url in image_items:
                disk_file = find_index_file(img_dir, gallery_name, idx)

                if disk_file:
                    if not s3_has_image(gallery_name, disk_file.name):
                        s3_upload_image(gallery_name, disk_file.name, disk_file)
                    img_count += 1
                    gallery_pbar.update(1)
                    continue

                found_remote = None
                for ext in (".jpg", ".png", ".webp", ".jpeg", ".gif"):
                    test = f"{gallery_name}-{idx}{ext}"
                    if s3_has_image(gallery_name, test):
                        found_remote = test
                        break

                if found_remote:
                    out_path = img_dir / found_remote
                    s3_restore_image(gallery_name, found_remote, out_path)
                    img_count += 1
                    gallery_pbar.update(1)
                    continue

                missing.append((idx, url))

            # ----- DOWNLOAD -----
            sem_img = asyncio.Semaphore(img_conc)

            async def img_worker(idx, url):
                nonlocal img_count
                async with sem_img:
                    await asyncio.to_thread(
                        download_file, url, str(img_dir), None, None, idx, gallery_name
                    )
                disk_file = find_index_file(img_dir, gallery_name, idx)
                if disk_file:
                    s3_upload_image(gallery_name, disk_file.name, disk_file)
                    img_count += 1
                gallery_pbar.update(1)

            if missing:
                await asyncio.gather(*(img_worker(idx, url) for idx, url in missing))

            gallery_pbar.close()
            stats[tag][gallery_name][0] = img_count
            if total_imgs > 0:
                safe_print(f"🖼️ {gallery_name:<45}|{img_count:>3}/{total_imgs:<3} images 🖼️")

    async def process_gallery_videos(link, tag, snippets):
        async with sem_gallery:
            raw_name = os.path.basename(urlparse(link).path.strip("/"))
            gallery_name = sanitize_gallery_name(raw_name)
            ensure(tag, gallery_name)

            root = settings.download_path
            vid_dir = Path(root) / tag / gallery_name / "videos"

            video_items = p2b_results.get(link, [])
            total_vids = len(video_items)
            vid_count = 0

            gallery_pbar = tqdm(
                total=total_vids,
                desc=f"🎞️ {gallery_name}"[:20].ljust(20),
                ncols=66,
                leave=False,
                position=0,
                bar_format="{l_bar}{bar}|{n_fmt:>3}/{total_fmt:<3} videos 🎞️",
            )

            missing = []

            # ----- PREPASS -----
            for idx, page_url in video_items:

                disk_file = find_index_file(vid_dir, gallery_name, idx)
                if disk_file:
                    if not s3_has_video(gallery_name, disk_file.name):
                        s3_upload_video(gallery_name, disk_file.name, disk_file)
                    vid_count += 1
                    gallery_pbar.update(1)
                    continue

                found_remote = None
                for ext in (".mp4", ".webm", ".mov", ".mkv", ".avi"):
                    test = f"{gallery_name}-{idx}{ext}"
                    if s3_has_video(gallery_name, test):
                        found_remote = test
                        break

                if found_remote:
                    out_path = vid_dir / found_remote
                    s3_restore_video(gallery_name, found_remote, out_path)
                    vid_count += 1
                    gallery_pbar.update(1)
                    continue

                missing.append((idx, page_url))

            p = None
            context = None

            # ----- DOWNLOAD -----
            if missing:
                p, context = await launch_chromium(headless=True)
                sem_vid = asyncio.Semaphore(vid_conc)

                async def vid_worker(idx, page_url):
                    nonlocal vid_count
                    async with sem_vid:
                        real_url = await resolve_video_page(context, page_url)
                    if not real_url:
                        gallery_pbar.update(1)
                        return

                    await asyncio.to_thread(
                        download_file, real_url, str(vid_dir), None, None, idx, gallery_name
                    )

                    disk_file = find_index_file(vid_dir, gallery_name, idx)
                    if disk_file:
                        s3_upload_video(gallery_name, disk_file.name, disk_file)
                        vid_count += 1

                    gallery_pbar.update(1)

                await asyncio.gather(*(vid_worker(idx, url) for idx, url in missing))

            gallery_pbar.close()
            stats[tag][gallery_name][1] = vid_count

            if context:
                await context.close()
            if p:
                await p.stop()

            if total_vids > 0:
                safe_print(f"🎞️ {gallery_name:<45}|{vid_count:>3}/{total_vids:<3} videos 🎞️")

    # ------------------------------------------------------------
    #  DISPATCH MODES
    # ------------------------------------------------------------
    if not INTERWOVEN:
        # Classic mode: all images → all videos
        await asyncio.gather(
            *(process_gallery_images(link, tag, snippets)
              for (link, tag, snippets) in ordered_galleries)
        )

        await asyncio.gather(
            *(process_gallery_videos(link, tag, snippets)
              for (link, tag, snippets) in ordered_galleries)
        )

        return stats

    # ============================================================
    #  INTERWOVEN MODE
    # ============================================================
    async def process_gallery_interwoven(entry):
        link, tag, snippets = entry
        await process_gallery_images(link, tag, snippets)
        await process_gallery_videos(link, tag, snippets)

    await asyncio.gather(
        *(process_gallery_interwoven(entry) for entry in ordered_galleries)
    )

    return stats
