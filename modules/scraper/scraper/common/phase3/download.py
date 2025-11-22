# ============================================================
#  download.py — Phase 3 (Images + Videos) — PURE PIPELINE
# ============================================================
import os
import asyncio
from urllib.parse import urlparse
from pathlib import Path
from tqdm import tqdm

from scraper.common.common import print_banner, launch_chromium, safe_print
import scraper.common.settings as settings

from scraper.common.phase3.download_file import download_file
from scraper.common.phase3.video_resolver import resolve_video_page


# ============================================================
#  DEBUG
# ============================================================
debug = True
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


# ============================================================
#  Prevent re-download (ANY extension)
# ============================================================
def index_file_exists(folder: str, gallery_name: str, idx: int) -> bool:
    prefix = f"{gallery_name}-{idx}"
    if not os.path.isdir(folder):
        return False
    for fname in os.listdir(folder):
        if fname.startswith(prefix):
            return True
    return False

# ============================================================
#  MASTER PHASE 3 — TRUE GALLERY CONCURRENCY
#  BUT STRICT ORDER: ALL IMAGES FIRST, THEN ALL VIDEOS
# ============================================================
async def phase3_download(
    ordered_galleries,
    p2a_results,
    p2b_results,
    interwoven=False
):
    print_banner("Phase 3 — Downloading", "🚀")
    dlog("\n==================== PHASE 3 START ====================\n")

    stats = {}

    def ensure(tag, gallery):
        if tag not in stats:
            stats[tag] = {}
        if gallery not in stats[tag]:
            stats[tag][gallery] = [0, 0]

    gallery_conc = getattr(settings, "GALLERY_CONC",
                           getattr(settings, "CONCURRENT_GALLERIES", 2))
    img_conc = getattr(settings, "IMG_CONC",
                       getattr(settings, "CONCURRENT_IMAGES_PER_GALLERY", 10))
    vid_conc = getattr(settings, "VID_CONC",
                       getattr(settings, "CONCURRENT_VIDEOS_PER_GALLERY", 5))

    sem_gallery = asyncio.Semaphore(gallery_conc)

    # ------------------------------------------------------------
    #  PHASE 3A — IMAGES
    # ------------------------------------------------------------
    print_banner("Phase 3A — Images", "🖼️")

    phase_bar_imgs = tqdm(
        total=len(ordered_galleries),
        desc="🖼️ Images",
        ncols=66,
        position=1,
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} galleries 🖼️",
        leave=True
    )

    async def process_gallery_images(link, tag, snippets):
        async with sem_gallery:
            gallery_name = os.path.basename(urlparse(link).path.strip("/"))
            ensure(tag, gallery_name)
            dlog(f"[IMG GALLERY] {gallery_name} ({tag})")

            root = settings.download_path
            img_dir = os.path.join(root, tag, gallery_name, "images")

            image_items = p2a_results.get(link, [])  # [(box_idx, url)]
            total_imgs = len(image_items)
            img_count = 0

            # Per-gallery tqdm
            gallery_pbar = tqdm(
                total=total_imgs,
                desc=f"🖼️ {gallery_name}"[:20].ljust(20),
                ncols=66,
                leave=False,
                position=0,
                bar_format="{l_bar}{bar}|{n_fmt:>3}/{total_fmt} images 🖼️"
            )

            sem_img = asyncio.Semaphore(img_conc)

            async def img_worker(box_idx: int, url: str):
                nonlocal img_count

                # Already have any extension for this index?
                if index_file_exists(img_dir, gallery_name, box_idx):
                    img_count += 1
                    gallery_pbar.update(1)
                    return

                async with sem_img:
                    ok = await asyncio.to_thread(
                        download_file, url, img_dir, None, None, box_idx, gallery_name
                    )

                # Tmp race tolerance: if tmp vanished and ok==False, just move on
                tmp_path = os.path.join(img_dir, f"{gallery_name}-{box_idx}.tmp")
                if ok or os.path.exists(tmp_path):
                    img_count += 1

                gallery_pbar.update(1)

            if image_items:
                await asyncio.gather(
                    *(img_worker(box_idx, url) for box_idx, url in image_items)
                )

            gallery_pbar.close()
            if total_imgs > 0:
                safe_print(
                    f"🖼️ {gallery_name:<45}|{img_count:>3}/{total_imgs:<3} images 🖼️"
                )

            stats[tag][gallery_name][0] = img_count
            phase_bar_imgs.update(1)

    # Run all image galleries with gallery concurrency
    await asyncio.gather(
        *(process_gallery_images(link, tag, snippets)
          for (link, tag, snippets) in ordered_galleries)
    )
    phase_bar_imgs.close()


    # ------------------------------------------------------------
    #  PHASE 3B — VIDEOS
    # ------------------------------------------------------------
    print_banner("Phase 3B — Videos", "🎞️")

    phase_bar_vids = tqdm(
        total=len(ordered_galleries),
        desc="🎞️ Videos",
        ncols=66,
        position=1,
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} galleries 🎞️",
        leave=True
    )

    async def process_gallery_videos(link, tag, snippets):
        async with sem_gallery:
            gallery_name = os.path.basename(urlparse(link).path.strip("/"))
            ensure(tag, gallery_name)
            dlog(f"[VID GALLERY] {gallery_name} ({tag})")

            root = settings.download_path
            vid_dir = os.path.join(root, tag, gallery_name, "videos")

            video_items = p2b_results.get(link, [])  # [(box_idx, page_url)]
            total_vids = len(video_items)
            vid_count = 0

            # Spin browser only if we actually have videos
            if total_vids > 0:
                p, context = await launch_chromium(
                    headless=True
                )
            else:
                p = context = None

            gallery_pbar = tqdm(
                total=total_vids,
                desc=f"🎞️ {gallery_name}"[:20].ljust(20),
                ncols=66,
                leave=False,
                position=0,
                bar_format="{l_bar}{bar}|{n_fmt:>3}/{total_fmt:<3} videos 🎞️"
            )

            sem_vid = asyncio.Semaphore(vid_conc)

            async def vid_worker(box_idx: int, page_url: str):
                nonlocal vid_count

                if index_file_exists(vid_dir, gallery_name, box_idx):
                    vid_count += 1
                    gallery_pbar.update(1)
                    return

                async with sem_vid:
                    real_url = await resolve_video_page(context, page_url)

                if not real_url:
                    gallery_pbar.update(1)
                    return

                ok = await asyncio.to_thread(
                    download_file, real_url, vid_dir, None, None, box_idx, gallery_name
                )

                tmp_path = os.path.join(vid_dir, f"{gallery_name}-{box_idx}.tmp")
                if ok or os.path.exists(tmp_path):
                    vid_count += 1

                gallery_pbar.update(1)

            if video_items:
                await asyncio.gather(
                    *(vid_worker(box_idx, page_url)
                      for box_idx, page_url in video_items)
                )

            gallery_pbar.close()
            if total_vids > 0:
                safe_print(
                    f"🎞️ {gallery_name:<45}|{vid_count:>3}/{total_vids:<3} videos 🎞️"
                )

            stats[tag][gallery_name][1] = vid_count

            if context is not None:
                await context.close()
            if p is not None:
                await p.stop()

            phase_bar_vids.update(1)

    # Run all video galleries with gallery concurrency
    await asyncio.gather(
        *(process_gallery_videos(link, tag, snippets)
          for (link, tag, snippets) in ordered_galleries)
    )
    phase_bar_vids.close()


    dlog("\n==================== PHASE 3 END ====================\n")
    return stats

