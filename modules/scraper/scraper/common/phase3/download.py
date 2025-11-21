# ============================================================
#  download.py — Phase 3 (Images + Videos) — PURE PIPELINE
# ============================================================
import os
import asyncio
from urllib.parse import urlparse
from tqdm import tqdm

from scraper.common.common import print_banner, launch_chromium, safe_print
import scraper.common.settings as settings

from scraper.common.phase3.download_file import download_file
from scraper.common.phase3.video_resolver import resolve_video_page
from pathlib import Path


# ============================================================
#  DEBUG LOGGING
# ============================================================
debug = True
PHASE3_DIR = Path(__file__).resolve().parent
PHASE3_DEBUG_FILE = PHASE3_DIR / "phase3_debug.txt"


def dlog(*args):
    """Write debug text into phase3_debug.txt"""
    if not debug:
        return
    try:
        with open(PHASE3_DEBUG_FILE, "a", encoding="utf-8") as f:
            f.write(" ".join(str(a) for a in args) + "\n")
    except:
        pass


# ============================================================
#  INDEX CHECK — prevents re-downloading files
# ============================================================
def index_file_exists(folder: str, gallery_name: str, idx: int) -> bool:
    """
    Checks if the file for this index already exists
    in the folder. Any extension is accepted.
    """
    prefix = f"{gallery_name}-{idx}"
    if not os.path.isdir(folder):
        return False

    for fname in os.listdir(folder):
        if fname.startswith(prefix):
            return True

    return False


# ============================================================
#  MASTER PHASE 3
# ============================================================
async def phase3_download(
    ordered_galleries,
    p2a_results,
    p2b_results,
    interwoven=False
):
    """
    ordered_galleries → [(link, tag, snippets), ...]
    p2a_results       → { link: [image_urls] }
    p2b_results       → { link: [video_page_urls] }
    """
    print_banner("Phase 3 — Downloading", "🚀")
    dlog("\n==================== PHASE 3 START ====================\n")

    stats = {}  # tag → { galleryName: [imgCount, vidCount] }

    def ensure(tag, gallery):
        if tag not in stats:
            stats[tag] = {}
        if gallery not in stats[tag]:
            stats[tag][gallery] = [0, 0]

    # ========================================================
    #  PHASE 3A — IMAGES
    # ========================================================
    print_banner("Phase 3A — Images", "🖼️")
    dlog("---- Phase 3A (Images) ----")

    with tqdm(total=len(ordered_galleries), desc="🖼️ Images", ncols=66) as bar:
        for (link, tag, snippets) in ordered_galleries:

            gallery_name = os.path.basename(urlparse(link).path.strip("/"))
            ensure(tag, gallery_name)
            dlog(f"\n[Gallery IMG] {gallery_name} ({tag})")

            root = settings.download_path
            gallery_root = os.path.join(root, tag, gallery_name)
            img_dir = os.path.join(gallery_root, "images")
            os.makedirs(img_dir, exist_ok=True)

            image_urls = p2a_results.get(link, [])
            img_count = 0

            for idx, url in enumerate(image_urls, start=1):

                # Already exists?
                if index_file_exists(img_dir, gallery_name, idx):
                    dlog(f"[SKIP IMG] idx={idx} exists — {url}")
                    img_count += 1
                    continue

                dlog(f"[DOWNLOAD IMG] idx={idx} → {url}")

                ok = await asyncio.to_thread(
                    download_file, url, img_dir, None, None, idx, gallery_name
                )
                if ok:
                    img_count += 1
                    dlog(f"[OK IMG] idx={idx}")
                else:
                    dlog(f"[FAIL IMG] idx={idx}")

            stats[tag][gallery_name][0] = img_count
            bar.update(1)

    # ========================================================
    #  PHASE 3B — VIDEOS
    # ========================================================
    print_banner("Phase 3B — Videos", "🎞️")
    dlog("\n---- Phase 3B (Videos) ----")

    with tqdm(total=len(ordered_galleries), desc="🎞️ Videos", ncols=66) as bar:
        for (link, tag, snippets) in ordered_galleries:

            gallery_name = os.path.basename(urlparse(link).path.strip("/"))
            ensure(tag, gallery_name)
            dlog(f"\n[Gallery VID] {gallery_name} ({tag})")

            root = settings.download_path
            gallery_root = os.path.join(root, tag, gallery_name)
            vid_dir = os.path.join(gallery_root, "videos")
            os.makedirs(vid_dir, exist_ok=True)

            video_pages = p2b_results.get(link, [])
            vid_count = 0

            # Launch Chromium once
            dlog(f"[CHROMIUM] launch for {gallery_name}")
            p, context = await launch_chromium(
                f"userdata/video_{gallery_name}",
                headless=True
            )

            for idx, page_url in enumerate(video_pages, start=1):

                if index_file_exists(vid_dir, gallery_name, idx):
                    dlog(f"[SKIP VID] idx={idx} exists — {page_url}")
                    vid_count += 1
                    continue

                dlog(f"[RESOLVE VID] idx={idx} → {page_url}")
                real_url = await resolve_video_page(context, page_url)

                if not real_url:
                    dlog(f"[FAIL RESOLVE] idx={idx}")
                    continue

                dlog(f"[DOWNLOAD VID] idx={idx} → {real_url}")
                ok = await asyncio.to_thread(
                    download_file, real_url, vid_dir, None, None, idx, gallery_name
                )

                if ok:
                    vid_count += 1
                    dlog(f"[OK VID] idx={idx}")
                else:
                    dlog(f"[FAIL VID] idx={idx}")

            stats[tag][gallery_name][1] = vid_count

            dlog(f"[CHROMIUM] close for {gallery_name}")
            await context.close()
            await p.stop()

            bar.update(1)

    dlog("\n==================== PHASE 3 END ====================\n")
    return stats
