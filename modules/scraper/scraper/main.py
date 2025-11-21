# ============================================================
#  FILE: scraper/main.py
#  Clean launcher for the entire TheFap Scraper pipeline.
# ============================================================

import os
import sys
import argparse
import asyncio
import shutil
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime
from tqdm import tqdm

# ------------------------------------------------------------
#  Dual-mode support (python main.py OR package import)
# ------------------------------------------------------------
if __package__ is None or __package__ == "":
    THIS_FILE = Path(__file__).resolve()
    SCRAPER_ROOT = THIS_FILE.parent
    PACKAGE_ROOT = SCRAPER_ROOT.parent
    sys.path.insert(0, str(PACKAGE_ROOT))
    __package__ = "scraper"

# ------------------------------------------------------------
#  Imports
# ------------------------------------------------------------
from .common.common import safe_print, print_banner, print_summary
from .common.phase1.scan_tags import phase1_collect_urls
from .common.phase1.scan_galleries import phase2_scan_galleries
from .common.phase3.download import phase3_download

import scraper.common.settings as settings
from scraper.common.settings import (
    load_global_defaults,
)
from .common import cache_db


# ============================================================
#  MAIN PIPELINE
# ============================================================
async def main(tags, galleries, reverse_flag, simulate_flag, summary_flag):
    # Load settings.ini into global variables
    load_global_defaults()

    # --------------------------------------------------------
    #  Phase 1 — Collect gallery URLs
    # --------------------------------------------------------
    if tags:
        tag_to_galleries, all_galleries = await phase1_collect_urls(tags)
    else:
        tag_to_galleries = {"manual": galleries}
        all_galleries = set(galleries)

    if not all_galleries:
        safe_print("❌ No galleries found for provided tags.")
        return

    # --------------------------------------------------------
    #  Phase 2 — Scroll each gallery and get snippets
    # --------------------------------------------------------
    gallery_data = await phase2_scan_galleries(tag_to_galleries)

    # Deduplicate by URL
    unique = {}
    for link, tag, snippets in gallery_data:
        if link not in unique:
            unique[link] = (link, tag, snippets)

    gallery_data = list(unique.values())

    # Filter by box count and sort
    gallery_data = sorted(
        [
            (link, tag, snippets, len(snippets))
            for link, tag, snippets in gallery_data
            if len(snippets) > settings.REQUIRED_MIN_BOXES
        ],
        key=lambda x: x[3],
        reverse=reverse_flag,
    )

    # Totals per tag
    tag_box_totals = {}
    for _, tag, _, count in gallery_data:
        tag_box_totals[tag] = tag_box_totals.get(tag, 0) + count

    # Build ordered list for Phase 3
    ordered = [
        (link, tag, snippets, count, tag_box_totals[tag])
        for (link, tag, snippets, count) in gallery_data
    ]

    # --------------------------------------------------------
    #  Phase 2 Summary
    # --------------------------------------------------------
    print_summary(
        f"Total galleries scanned: {len(unique)}",
        f"Total boxes extracted: {sum(len(snippets) for _, _, snippets in unique.values())}",
        f"Required min boxes: {settings.REQUIRED_MIN_BOXES}",
        f"Accepted galleries: {len(gallery_data)}",
        emoji="🌐",
    )

    # --------------------------------------------------------
    #  Phase 3 — Download Images + Videos
    # --------------------------------------------------------
    if ordered and not simulate_flag:
        stats = await phase3_download(ordered, settings.INTERWOVEN_MODE)
    else:
        print_banner("Simulation Mode — Downloads Skipped", "🧪")
        stats = {}

    # --------------------------------------------------------
    #  Phase 4 — Cleanup temporary folders
    # --------------------------------------------------------
    print_banner("Phase 4/4 — Cleanup", "🧹")

    for target in ["__pycache__", "userdata"]:
        if not os.path.exists(target):
            continue

        folders = [
            os.path.join(target, d)
            for d in os.listdir(target)
            if os.path.isdir(os.path.join(target, d))
        ]

        with tqdm(total=len(folders), desc=f"🧹 {target}") as bar:
            for folder in folders:
                shutil.rmtree(folder, ignore_errors=True)
                bar.update(1)

        shutil.rmtree(target, ignore_errors=True)

    print_banner("Cleanup Complete", "✅")

    # --------------------------------------------------------
    #  Final Summary
    # --------------------------------------------------------
    if summary_flag and stats:
        print_banner("Download Summary", "📦")
        for tag, gdata in stats.items():
            total_images = sum(v[0] for v in gdata.values())
            total_videos = sum(v[1] for v in gdata.values())
            safe_print(f"📦 {tag:<32} | {total_images} images, {total_videos} videos")
        safe_print("📦 " + "═" * 60 + " 📦")


# ============================================================
#  ENTRY POINT
# ============================================================
if __name__ == "__main__":
    load_global_defaults()
    asyncio.run(cache_db.init_db())

    # --------------- CLI ---------------
    parser = argparse.ArgumentParser(description="Ultimate TheFap Scraper")

    parser.add_argument("tags", nargs="*", help="Search tags")
    parser.add_argument("-g", "--galleries", nargs="+", help="Specific gallery URLs")
    parser.add_argument("--tags-file", help="Load tags from file (one per line)")
    parser.add_argument("--galleries-file", help="Load gallery URLs from file")
    parser.add_argument("--last", nargs="?", const="all", help="Load last N tags used")

    args = parser.parse_args()

    # Load tags
    tags = args.tags or []
    galleries = args.galleries or []

    if args.tags_file:
        tags.extend([t.strip() for t in open(args.tags_file).read().splitlines()])

    if args.galleries_file:
        galleries.extend([g.strip() for g in open(args.galleries_file).read().splitlines()])

    # Load from DB history
    if args.last:
        if args.last == "all":
            tags = asyncio.run(cache_db.get_last(None))
        else:
            tags = asyncio.run(cache_db.get_last(int(args.last)))

    tags = sorted({t.lower() for t in tags if t.strip()})

    if not tags and not galleries:
        print("❌ Provide tags or galleries.")
        sys.exit(1)

    # Start banner
    print_summary(
        "TheFap Gallery Downloader",
        f"Tags: {len(tags)}",
        f"Galleries: {len(galleries)}",
        emoji="🧭",
    )

    asyncio.run(
        main(
            tags=tags,
            galleries=galleries,
            reverse_flag=False,
            simulate_flag=False,
            summary_flag=True,
        )
    )
