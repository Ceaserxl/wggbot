# ============================================================
#  download.py — Phase 3 (Images + Videos)
#  Location: scraper/common/phase3/download.py
# ============================================================

import os
from urllib.parse import urlparse
from tqdm import tqdm

from scraper.common.common import print_banner
from scraper.common.settings import (
    download_path,
    IMG_CONC,
    VID_CONC,
    INTERWOVEN_MODE,
)

from scraper.common.phase2.images import process_images
from scraper.common.phase2.videos import process_videos


# ============================================================
#  PHASE 3 — Download all images + videos
# ============================================================
async def phase3_download(ordered_galleries, interwoven: bool | None = None):
    """
    ordered_galleries = [
        (link, tag, snippets, box_count, tag_total)
    ]
    """
    print_banner("Phase 3 — Downloading", "🚀")

    if interwoven is None:
        interwoven = INTERWOVEN_MODE

    stats = {}  # tag → { gallery → [image_count, video_count] }

    def ensure(tag: str, gallery: str):
        if tag not in stats:
            stats[tag] = {}
        if gallery not in stats[tag]:
            stats[tag][gallery] = [0, 0]

    # ============================================================
    #  INTERWOVEN MODE
    # ============================================================
    if interwoven:
        with tqdm(total=len(ordered_galleries), desc="🚀 Galleries", ncols=66) as bar:

            for link, tag, snippets, box_count, tag_total in ordered_galleries:
                gallery_name = os.path.basename(urlparse(link).path.strip("/"))
                ensure(tag, gallery_name)

                root = download_path
                gallery_root = f"{tag_total}-{tag}/{box_count}-{gallery_name}"

                # ---------------- Images
                img_dir = os.path.join(root, "images", gallery_root, "images")
                os.makedirs(img_dir, exist_ok=True)

                img_count = await process_images(
                    snippets=snippets,
                    out_dir=img_dir,
                    gallery_name=gallery_name,
                    concurrency=IMG_CONC,
                )
                stats[tag][gallery_name][0] += img_count

                # ---------------- Videos
                vid_dir = os.path.join(root, "videos", gallery_root, "videos")
                os.makedirs(vid_dir, exist_ok=True)

                vid_count = await process_videos(
                    snippets=snippets,
                    out_dir=vid_dir,
                    gallery_name=gallery_name,
                    concurrency=VID_CONC,
                )
                stats[tag][gallery_name][1] += vid_count

                bar.update(1)

        return stats

    # ============================================================
    #  SPLIT MODE (Images → Videos)
    # ============================================================

    # ---------------- Images Pass
    print_banner("Phase 3A — Images", "🖼️")
    with tqdm(total=len(ordered_galleries), desc="🖼️ Images", ncols=66) as bar:

        for link, tag, snippets, box_count, tag_total in ordered_galleries:
            gallery_name = os.path.basename(urlparse(link).path.strip("/"))
            ensure(tag, gallery_name)

            root = download_path
            gallery_root = f"{tag_total}-{tag}/{box_count}-{gallery_name}"

            img_dir = os.path.join(root, "images", gallery_root, "images")
            os.makedirs(img_dir, exist_ok=True)

            img_count = await process_images(
                snippets=snippets,
                out_dir=img_dir,
                gallery_name=gallery_name,
                concurrency=IMG_CONC,
            )
            stats[tag][gallery_name][0] += img_count
            bar.update(1)

    # ---------------- Videos Pass
    print_banner("Phase 3B — Videos", "🎞️")
    with tqdm(total=len(ordered_galleries), desc="🎞️ Videos", ncols=66) as bar:

        for link, tag, snippets, box_count, tag_total in ordered_galleries:
            gallery_name = os.path.basename(urlparse(link).path.strip("/"))
            ensure(tag, gallery_name)

            root = download_path
            gallery_root = f"{tag_total}-{tag}/{box_count}-{gallery_name}"

            vid_dir = os.path.join(root, "videos", gallery_root, "videos")
            os.makedirs(vid_dir, exist_ok=True)

            vid_count = await process_videos(
                snippets=snippets,
                out_dir=vid_dir,
                gallery_name=gallery_name,
                concurrency=VID_CONC,
            )
            stats[tag][gallery_name][1] += vid_count
            bar.update(1)

    return stats
