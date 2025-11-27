# ============================================================
#  FILE: scraper/main.py
#  Clean launcher for full TheFap Scraper pipeline.
#  Pipeline: P1A → P1B → P2A → P2B → P3
# ============================================================

import os
import sys
import argparse
import asyncio
import shutil
from pathlib import Path
from tqdm import tqdm

# ------------------------------------------------------------
#  Dual mode import support
# ------------------------------------------------------------
if __package__ is None or __package__ == "":
    THIS_FILE = Path(__file__).resolve()
    SCRAPER_ROOT = THIS_FILE.parent
    PACKAGE_ROOT = SCRAPER_ROOT.parent
    sys.path.insert(0, str(PACKAGE_ROOT))
    __package__ = "scraper"

# ------------------------------------------------------------
#  PRE-RUN: wipe all *_debug.txt logs
# ------------------------------------------------------------
project_root = Path(__file__).resolve().parent.parent

def wipe_debug_logs():
    for root, dirs, files in os.walk(project_root):
        for f in files:
            if f.endswith("_debug.txt"):
                try:
                    p = Path(root) / f
                    p.unlink(missing_ok=True)
                except:
                    pass

# ------------------------------------------------------------
#  Imports
# ------------------------------------------------------------
from .common.common import safe_print, print_banner, print_summary
from .phase1.scan_tags import phase1A_collect_urls
from .phase1.scan_galleries import phase1B_scan_galleries
from .phase2.extract_images import extract_images_from_boxes
from .phase2.extract_videos import extract_videos_from_boxes
from .phase3.download import phase3_download

import scraper.common.settings as settings
from scraper.common.settings import load_global_defaults
from .common import cache_db

# ============================================================
#  MAIN PIPELINE — strict P1A → P1B → P2A → P2B → P3
# ============================================================
async def main(tags, galleries, reverse_flag, simulate_flag, summary_flag):
    load_global_defaults()

    phase1_enabled = True
    phase2_enabled = True
    phase3_enabled = True

    # -----------------------------
    # PHASE 1A + 1B
    # -----------------------------
    if phase1_enabled:

        # -------------------------
        #  Phase 1A — get gallery URLs
        # -------------------------
        if tags:
            tag_to_galleries, all_galleries = await phase1A_collect_urls(tags)
            # Save tags to history
            for t in tags:
                await cache_db.save_last_tag(t)
        else:
            tag_to_galleries = {"manual": galleries}
            all_galleries = set(galleries)

        if not all_galleries:
            safe_print("❌ No galleries found.")
            return
        # -------------------------
        #  Phase 1B — scroll galleries → snippets
        # -------------------------
        p1b_results = await phase1B_scan_galleries(tag_to_galleries)

        # Deduplicate by gallery URL
        deduped = {}
        for link, tag, snippets in p1b_results:
            if link not in deduped:
                deduped[link] = (link, tag, snippets)

        # Clean + filter
        galleries_clean = [
            (link, tag, snippets)
            for (link, tag, snippets) in deduped.values()
            if len(snippets) > settings.REQUIRED_MIN_BOXES
        ]

    # -----------------------------
    # PHASE 2A + 2B
    # -----------------------------
    if phase2_enabled:

        # -------------------------
        #  Phase 2A — Extract image URLs
        # -------------------------
        print_banner("Phase 2 — Evaluating & Sorting...", "📦")
        p2a_results = {}   # gallery → [imageURLs]

        for link, tag, snippets in galleries_clean:
            image_urls = await extract_images_from_boxes(snippets)
            p2a_results[link] = image_urls
        # -------------------------
        #  Phase 2B — Extract video PAGE URLs
        # -------------------------
        p2b_results = {}   # gallery → [videoPageURLs]

        for link, tag, snippets in galleries_clean:
            video_pages = await extract_videos_from_boxes(snippets)
            p2b_results[link] = video_pages

        # -------------------------
        #  Build Phase 3 input list
        # -------------------------
        ordered = [
            (link, tag, snippets)
            for (link, tag, snippets) in galleries_clean
        ]
        # ✅ Sort galleries by snippet count (least → most)
        ordered.sort(key=lambda x: len(x[2]))

        print_summary(
            f"Min boxes: {settings.REQUIRED_MIN_BOXES}",
            f"Accepted galleries: {len(galleries_clean)}",
            emoji="🌐",
        )

    # -----------------------------
    # PHASE 3 (disabled for now)
    # -----------------------------
    if phase3_enabled:
        if ordered and not simulate_flag:
            stats = await phase3_download(
                ordered_galleries=ordered,
                p2a_results=p2a_results,
                p2b_results=p2b_results,
                interwoven=settings.INTERWOVEN_MODE
            )
        else:
            print_banner("Simulation Mode — Skipped", "🧪")
            stats = {}

    # -----------------------------
    # PHASE 4 — CLEANUP
    # -----------------------------
    print_banner("Phase 4 — Cleanup", "🧹")

    # Remove __pycache__ everywhere
    pycaches = []
    for root, dirs, files in os.walk(project_root):
        for d in dirs:
            if d == "__pycache__":
                pycaches.append(os.path.join(root, d))

    for folder in pycaches:
        shutil.rmtree(folder, ignore_errors=True)

    # Remove userdata
    if os.path.exists("userdata"):
        shutil.rmtree("userdata", ignore_errors=True)

    print_banner("Cleanup Complete", "✅")

    # -----------------------------
    # Phase 3 Summary (only if enabled)
    # -----------------------------
    if phase3_enabled and summary_flag and stats:
        print_banner("Tag Download Summary", "📦")
        for tag, gdata in stats.items():
            imgs = sum(v[0] for v in gdata.values())
            vids = sum(v[1] for v in gdata.values())
            safe_print(f"📦 {tag:<37} | {imgs} images, {vids} videos 📦")
        safe_print("📦 " + "═" * 60 + " 📦")

# ============================================================
#  ENTRY POINT
# ============================================================
if __name__ == "__main__":
    load_global_defaults()
    asyncio.run(cache_db.init_db())

    parser = argparse.ArgumentParser(description="Ultimate TheFap Scraper")
    parser.add_argument("tags", nargs="*", help="Search tags")
    parser.add_argument("-g", "--galleries", nargs="+")
    parser.add_argument("--tags-file")
    parser.add_argument("--galleries-file")
    parser.add_argument("--last", nargs="?", const="all")
    parser.add_argument("--export", action="store_true", help="Export DB tables to ./export")

    args = parser.parse_args()

    # =======================
    # 1. EXPORT MODE ONLY
    # =======================
    if args.export:
        print("📤 Exporting database tables to ./export ...")
        asyncio.run(cache_db.export_all_tables("export"))
        print("✅ Export complete.")
        sys.exit(0)

    # =======================
    # 2. NORMAL MODE
    # =======================
    tags = list(args.tags) if args.tags else []
    galleries = list(args.galleries) if args.galleries else []

    # --- Load tags from file ---
    if args.tags_file:
        try:
            with open(args.tags_file, "r", encoding="utf-8") as f:
                tags.extend([t.strip() for t in f.readlines() if t.strip()])
        except:
            print(f"❌ Failed to read tags file: {args.tags_file}")
            sys.exit(1)

    # --- Load galleries from file ---
    if args.galleries_file:
        try:
            with open(args.galleries_file, "r", encoding="utf-8") as f:
                galleries.extend([g.strip() for g in f.readlines() if g.strip()])
        except:
            print(f"❌ Failed to read galleries file: {args.galleries_file}")
            sys.exit(1)

    # --- Handle --last ---
    if args.last is not None:
        val = str(args.last).strip().lower()

        if val == "" or val == "all":
            tags = asyncio.run(cache_db.get_last(None))
        else:
            try:
                n = int(val)
                tags = asyncio.run(cache_db.get_last(n))
            except ValueError:
                print(f"❌ Invalid --last value: {args.last}")
                sys.exit(1)

        tags = tags or []

    # --- Normalize tags ---
    tags = sorted({t.lower() for t in tags if t.strip()})

    if not tags and not galleries:
        print("❌ Provide tags or galleries.")
        sys.exit(1)

    print_summary(
        "TheFap Gallery Downloader",
        f"Loaded Tags: {len(tags)}",
        emoji="🧭",
    )

    print_banner("Phase 0 - Pre Cleaning...")
    wipe_debug_logs()

    asyncio.run(
        main(
            tags,
            galleries,
            reverse_flag=False,
            simulate_flag=False,
            summary_flag=True
        )
    )
