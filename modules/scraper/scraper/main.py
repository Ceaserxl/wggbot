# ------------------------------------------------------------
#  Dual-mode import support (run as script OR module)
# ------------------------------------------------------------
import os
import sys
from pathlib import Path

# If running directly (python main.py)
if __package__ is None or __package__ == "":
    # Force Python to treat this directory as a package root
    THIS_FILE = Path(__file__).resolve()
    SCRAPER_ROOT = THIS_FILE.parent          # modules/scraper/scraper/
    PACKAGE_ROOT = SCRAPER_ROOT.parent       # modules/scraper/

    sys.path.insert(0, str(PACKAGE_ROOT))

    # Fix __package__ so relative imports work
    __package__ = "scraper"

import argparse
import asyncio
import signal
import requests
import threading
import shutil
import time
import aiohttp
import configparser
import platform
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from tqdm import tqdm
from .common.images import process_images
from .common.videos import process_videos
from .common.common import launch_chromium, download_file
from .common import cache_db

import json
import hashlib
from datetime import datetime, timedelta

# ============================================================
#  Configuration
# ============================================================
BASE_URL = "https://thefap.net/search/{}/"
BASE_DOMAIN = "https://thefap.net"
from pathlib import Path
import os

# Root of the scraper package (modules/scraper/scraper/)
SCRAPER_ROOT = Path(__file__).resolve().parent
SETTINGS_PATH = SCRAPER_ROOT / "settings.ini"

CACHE_DIR      = SCRAPER_ROOT / "cache"
os.makedirs(CACHE_DIR, exist_ok=True)
CACHE_DAYS = 70
TAG_CACHE_DAYS = 70

BANNER_WIDTH = 60

if os.name == "nt":
    download_path = SCRAPER_ROOT / "downloads_win"
else:
    download_path = SCRAPER_ROOT / "downloads"
# ============================================================
#  GLOBAL DEFAULT VARIABLES (used when running as module)
# ============================================================

# numeric limits
PROCESS_IMAGES = 10
PROCESS_VIDEOS = 10
PROCESS_GALLERIES = 1
SCAN_TAGS = 25
SCAN_GALLERIES = 25
MIN_BOXES = 0

# boolean defaults
ini_reverse = False
ini_simulate = False
ini_imagesvideos = False
ini_summary = True
ini_videosonly = False
ini_imagesonly = False
ini_videosfirst = False


def load_global_defaults():
    """
    Loads settings.ini and updates all global variables.
    This must be called before running main() when the scraper
    is imported (Discord bot).
    """
    global PROCESS_IMAGES, PROCESS_VIDEOS, PROCESS_GALLERIES
    global SCAN_TAGS, SCAN_GALLERIES, MIN_BOXES
    global ini_reverse, ini_simulate, ini_imagesvideos
    global ini_summary, ini_videosonly, ini_imagesonly, ini_videosfirst

    ensure_settings_file()
    settings = load_settings()

    PROCESS_IMAGES     = settings["PROCESS_IMAGES"]
    PROCESS_VIDEOS     = settings["PROCESS_VIDEOS"]
    PROCESS_GALLERIES  = settings["PROCESS_GALLERIES"]
    SCAN_TAGS          = settings["SCAN_TAGS"]
    SCAN_GALLERIES     = settings["SCAN_GALLERIES"]
    MIN_BOXES          = settings["MIN_BOXES"]

    ini_reverse       = settings["reverse"]
    ini_simulate      = settings["simulate"]
    ini_imagesvideos  = settings["images_videos"]
    ini_summary       = settings["summary"]
    ini_videosonly    = settings["videos_only"]
    ini_imagesonly    = settings["images_only"]
    ini_videosfirst   = settings["videos_first"]


# ============================================================
#  Settings Parser + Defaults
# ============================================================

DEFAULT_LIMITS = {
    "process_images": "10",
    "process_videos": "10",
    "process_galleries": "1",
    "scan_tags": "25",
    "scan_galleries": "25",
    "min_boxes": "0",
}

DEFAULT_FLAGS = {
    "reverse": "false",
    "simulate": "false",
    "images_videos": "false",
    "summary": "true",
    "videos_only": "false",
    "images_only": "false",
    "videos_first": "false",
}

def ensure_settings_file():
    if not os.path.exists(SETTINGS_PATH):
        config = configparser.ConfigParser()

        config["limits"] = DEFAULT_LIMITS
        config["flags"]  = DEFAULT_FLAGS

        with open(SETTINGS_PATH, "w") as f:
            config.write(f)

def to_bool(v):
    return str(v).lower() in ("1", "true", "yes", "on")

def load_settings():
    config = configparser.ConfigParser()
    config.read(SETTINGS_PATH)

    # Ensure both sections always exist
    if "limits" not in config:
        config["limits"] = DEFAULT_LIMITS
    if "flags" not in config:
        config["flags"] = DEFAULT_FLAGS

    limits = config["limits"]
    flags  = config["flags"]

    settings = {
        # Numeric
        "PROCESS_IMAGES": int(limits.get("process_images", "10")),
        "PROCESS_VIDEOS": int(limits.get("process_videos", "10")),
        "PROCESS_GALLERIES": int(limits.get("process_galleries", "1")),
        "SCAN_TAGS": int(limits.get("scan_tags", "25")),
        "SCAN_GALLERIES": int(limits.get("scan_galleries", "25")),
        "MIN_BOXES": int(limits.get("min_boxes", "0")),

        # Boolean flags
        "reverse":       to_bool(flags.get("reverse", "false")),
        "simulate":      to_bool(flags.get("simulate", "false")),
        "images_videos": to_bool(flags.get("images_videos", "false")),
        "summary":       to_bool(flags.get("summary", "true")),
        "videos_only":   to_bool(flags.get("videos_only", "false")),
        "images_only":   to_bool(flags.get("images_only", "false")),
        "videos_first":  to_bool(flags.get("videos_first", "false")),
    }

    return settings


def update_setting(key, value):
    """
    Automatically updates either:
      [limits] or [flags]
    depending on which category the key belongs to.
    """

    config = configparser.ConfigParser()
    config.read(SETTINGS_PATH)

    # Ensure sections
    if "limits" not in config:
        config["limits"] = DEFAULT_LIMITS
    if "flags" not in config:
        config["flags"] = DEFAULT_FLAGS

    # Which bucket does this key belong to?
    if key in DEFAULT_LIMITS:
        config["limits"][key] = str(value)
    elif key in DEFAULT_FLAGS:
        config["flags"][key] = str(value)
    else:
        print(f"❌ Unknown setting '{key}'")
        sys.exit(1)

    with open(SETTINGS_PATH, "w") as f:
        config.write(f)

    print(f"✔ Updated {key} = {value} in settings.ini")

def get_missing_images(gallery_dir: str, total_expected: int, gallery_name: str):
    """
    Compare files on disk with expected image count.
    Returns a list of missing indices.
    """
    if not os.path.exists(gallery_dir):
        return list(range(1, total_expected + 1))

    present_indices = set()

    for f in os.listdir(gallery_dir):
        if f.startswith(gallery_name + "-"):
            part = f.split("-")[-1]
            idx_str = part.split(".")[0]

            if idx_str.isdigit():
                present_indices.add(int(idx_str))

    missing = [i for i in range(1, total_expected + 1) if i not in present_indices]
    return missing

# ============================================================
#  Thread-safe printing
# ============================================================
from rich.console import Console
from io import StringIO

console = Console(file=StringIO(), force_terminal=True, color_system="auto")

print_lock = threading.Lock()
def safe_print(*args, **kwargs):
    """Thread-safe print that supports Rich markup but preserves tqdm formatting."""
    with print_lock:
        buf = StringIO()
        temp_console = Console(file=buf, force_terminal=True, color_system="auto")
        temp_console.print(*args, **kwargs)
        output = buf.getvalue().rstrip("\n")
        tqdm.write(output)

# ============================================================
#  Immediate Ctrl +C handler
# ============================================================
stop_event = asyncio.Event()
def _sigint_handler(signum, frame):
    print("\n🛑 Ctrl+C detected — terminating all tasks...")
    for task in asyncio.all_tasks():
        task.cancel()
    try:
        stop_event.set()
    except Exception:
        pass
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(1)

signal.signal(signal.SIGINT, _sigint_handler)
signal.signal(signal.SIGTERM, _sigint_handler)
# ============================================================
#  Tag history
# ============================================================
def add_tags_to_history(tags, file_path="last.txt"):
    existing = set()
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            existing = {line.strip().lower() for line in f if line.strip()}

    new_tags = [t for t in tags if t.lower() not in existing]
    if new_tags:
        with open(file_path, "a", encoding="utf-8") as f:
            for t in new_tags:
                f.write(t + "\n")

# ============================================================
#  Banner helpers
# ============================================================
def print_banner(title, emoji="🔷", min_width=BANNER_WIDTH, char="═"):
    width = max(min_width, len(title) + 8)
    border = char * width
    centered = title.center(width)
    centered = centered[:width] if len(centered) > width else centered.ljust(width)
    safe_print(f"{emoji} {border} {emoji}")
    safe_print(f"{emoji} {centered} {emoji}")
    safe_print(f"{emoji} {border} {emoji}")

def print_subbanner(title, emoji="📁", min_width=BANNER_WIDTH, char="─"):
    width = max(min_width, len(title) + 8)
    border = char * width
    centered = title.center(width)
    centered = centered[:width] if len(centered) > width else centered.ljust(width)
    safe_print(f"{emoji} {border} {emoji}")
    safe_print(f"{emoji} {centered} {emoji}")
    safe_print(f"{emoji} {border} {emoji}")

def print_summary(*lines, emoji="📄", min_width=BANNER_WIDTH, char="═"):
    max_len = max(len(line) for line in lines) if lines else 0
    width = max(min_width, max_len + 8)
    border = char * width
    safe_print(f"{emoji} {border} {emoji}")
    for line in lines:
        centered = line.center(width)
        centered = centered[:width] if len(centered) > width else centered.ljust(width)
        safe_print(f"{emoji} {centered} {emoji}")
    safe_print(f"{emoji} {border} {emoji}")

# ============================================================
#  Phase 1 — Collect gallery links (per-tag)
# ============================================================
async def get_links(session, tag: str):
    cached_links = await cache_db.load_tag(tag, TAG_CACHE_DAYS)
    if cached_links is not None:
        return cached_links

    url = BASE_URL.format(tag)
    async with session.get(url, timeout=60) as r:
        text = await r.text()

    soup = BeautifulSoup(text, "html.parser")
    boxes = soup.find_all("div", class_="bg-red-400")
    links = []
    for box in boxes:
        a = box.find("a", href=True)
        if a:
            href = a["href"]
            if href.startswith("/"):
                href = BASE_DOMAIN + href
            links.append(href)

    if links:
        await cache_db.save_tag(tag, links, TAG_CACHE_DAYS)
    return links

async def phase1_collect_urls(tags):
    print_banner("Phase 1 — Collecting URLs", "🔍")

    tag_to_galleries = {}
    all_galleries = set()

    queue = asyncio.Queue()
    for tag in tags:
        queue.put_nowait(tag)

    async with aiohttp.ClientSession() as session:
        async def worker(pbar):
            while True:
                try:
                    tag = await queue.get()
                except asyncio.CancelledError:
                    return
                try:
                    links = await get_links(session, tag)
                    tag_to_galleries[tag] = links
                    all_galleries.update(links)
                except Exception as e:
                    safe_print(f"❌ Failed tag {tag}: {e}")
                finally:
                    pbar.update(1)
                    queue.task_done()

        with tqdm(
            total=len(tags),
            desc="🔍 Tags",
            position=0,
            ncols=66,
            leave=True,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} 🔍"
        ) as t1:
            workers = [
                asyncio.create_task(worker(t1))
                for _ in range(min(SCAN_TAGS, max(1, len(tags))))
            ]
            await queue.join()
            for w in workers:
                w.cancel()

    return tag_to_galleries, list(all_galleries)

# ============================================================
#  Phase 2 — Scroll galleries
# ============================================================
async def scroll_gallery(context, url, delay=1000):
    page = await context.new_page()
    await page.goto(url, timeout=180000)

    last_count, same_rounds = 0, 0
    while True:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(delay)
        boxes = await page.query_selector_all("#content > div")
        count = len(boxes)

        if count == last_count:
            same_rounds += 1
            if same_rounds >= 2:
                break
        else:
            same_rounds, last_count = 0, count

        if stop_event.is_set():
            raise asyncio.CancelledError

    return page, boxes

async def scrape_gallery_boxes(link, tag):
    cached = await cache_db.load_gallery(link, CACHE_DAYS)
    if cached is not None:
        return (link, tag, cached)

    gallery_name = os.path.basename(urlparse(link).path.strip("/"))
    try:
        p, context = await launch_chromium(f"userdata/userdata_{gallery_name}", headless=True)
        page, boxes = await scroll_gallery(context, link)
        snippets = [await b.evaluate("el => el.outerHTML") for b in boxes]
        await page.close()
        await context.close()
        await p.stop()
        if snippets:
            await cache_db.save_gallery(link, tag, snippets, CACHE_DAYS)
        return (link, tag, snippets)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        safe_print(f"❌ Failed to scrape {gallery_name}: {e}")
        return (link, tag, [])

async def phase2_scan_galleries(tag_to_galleries):
    all_gallery_tasks = [(link, tag) for tag, glist in tag_to_galleries.items() for link in glist]
    print_banner(f"Phase 2 — Scanning {len(all_gallery_tasks)} Galleries", "🌐")

    queue = asyncio.Queue()
    for link, tag in all_gallery_tasks:
        queue.put_nowait((link, tag))

    results = []

    async def worker(pbar):
        while True:
            try:
                link, tag = await queue.get()
            except asyncio.CancelledError:
                return
            try:
                data = await scrape_gallery_boxes(link, tag)
                if data[2]:
                    results.append(data)
            except Exception as e:
                safe_print(f"❌ failed gallery {link}: {e}")
            finally:
                pbar.update(1)
                queue.task_done()

    with tqdm(
        total=len(all_gallery_tasks),
        desc="🌐 Scanning Galleries",
        position=0,
        ncols=66,
        leave=True,
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} 🌐"
    ) as t2:
        workers = [
            asyncio.create_task(worker(t2))
            for _ in range(min(SCAN_GALLERIES, max(1, len(all_gallery_tasks))))
        ]
        await queue.join()
        for w in workers:
            w.cancel()

    return results

# ============================================================
#  Phase 3 — Download content
# ============================================================
async def download_gallery_images(link, tag, snippets, box_count, tag_total):
    async with semaphore_galleries:
        gallery_name = os.path.basename(urlparse(link).path.strip("/"))
        tag_folder   = f"{tag_total}-{tag}"
        base_dir     = os.path.join(download_path, "images", tag_folder, f"{box_count}-{gallery_name}", "images")

        per_gallery_image_conc = max(1, PROCESS_IMAGES)

        async def process_once():
            p, context = await launch_chromium(f"userdata/{gallery_name}_img", headless=True)
            page = await context.new_page()
            await page.set_content("<html><body>" + "".join(snippets) + "</body></html>", timeout=60000)

            # extract all boxes with images
            boxes = await page.query_selector_all("body > div")
            image_boxes = []
            for b in boxes:
                img = await b.query_selector("img")
                if img:
                    image_boxes.append(b)

            total_expected = len(image_boxes)

            # ensure folder exists
            os.makedirs(base_dir, exist_ok=True)

            # find already downloaded indexes
            existing = set()
            for f in os.listdir(base_dir):
                if f.startswith(gallery_name + "-"):
                    idx = f.split("-")[-1].split(".")[0]
                    if idx.isdigit():
                        existing.add(int(idx))

            missing_indexes = sorted(set(range(1, total_expected + 1)) - existing)

            if not missing_indexes:
                await context.close()
                await p.stop()
                return 0

            # build list of (idx, box) to download
            missing_boxes = [
                (idx, image_boxes[idx - 1])
                for idx in missing_indexes
            ]

            sem = asyncio.Semaphore(per_gallery_image_conc)
            results = []

            async def download_one(idx, box):
                async with sem:
                    img = await box.query_selector("img")
                    if not img:
                        return False

                    src = await img.get_attribute("src")
                    if not src:
                        return False

                    return await asyncio.to_thread(
                        download_file,
                        src,
                        base_dir,
                        None,
                        None,
                        idx,
                        gallery_name
                    )

            for idx, box in missing_boxes:
                results.append(download_one(idx, box))

            finished = await asyncio.gather(*results)
            await context.close()
            await p.stop()
            return sum(1 for x in finished if x)

        try:
            return await process_once()
        except Exception as e:
            safe_print(f"⚠️ Retry images for {gallery_name}: {e}")
            await asyncio.sleep(1)
            try:
                return await process_once()
            except:
                safe_print(f"❌ Image phase failed for {gallery_name}")
                return 0

async def download_gallery_videos(link, tag, snippets, box_count, tag_total):
    async with semaphore_galleries:
        gallery_name = os.path.basename(urlparse(link).path.strip("/"))
        tag_folder   = f"{tag_total}-{tag}"
        base_dir     = os.path.join(download_path, "videos", tag_folder, f"{box_count}-{gallery_name}", "videos")

        per_gallery_video_conc = max(1, PROCESS_VIDEOS)

        async def process_once():
            p, context = await launch_chromium(None, headless=True)
            page = await context.new_page()
            await page.set_content("<html><body>" + "".join(snippets) + "</body></html>", timeout=60000)

            boxes = await page.query_selector_all("body > div")
            video_boxes = []
            for b in boxes:
                play_icon = await b.query_selector("img[src*='icon-play.svg']")
                if play_icon:
                    video_boxes.append(b)

            total_expected = len(video_boxes)

            os.makedirs(base_dir, exist_ok=True)

            existing = set()
            for f in os.listdir(base_dir):
                if f.startswith(gallery_name + "-"):
                    idx = f.split("-")[-1].split(".")[0]
                    if idx.isdigit():
                        existing.add(int(idx))

            missing_indexes = sorted(set(range(1, total_expected + 1)) - existing)

            if not missing_indexes:
                await context.close()
                await p.stop()
                return 0

            missing_boxes = [
                (idx, video_boxes[idx - 1])
                for idx in missing_indexes
            ]

            sem = asyncio.Semaphore(per_gallery_video_conc)

            async def download_one(idx, box):
                async with sem:
                    # process_videos expects list[box]
                    return await process_videos(
                        [box],
                        base_dir,
                        gallery_name,
                        1,
                        context=context
                    )

            tasks = [download_one(idx, b) for idx, b in missing_boxes]
            results = await asyncio.gather(*tasks)

            await context.close()
            await p.stop()
            return sum(results)

        try:
            return await process_once()
        except Exception as e:
            safe_print(f"⚠️ Retry videos for {gallery_name}: {e}")
            await asyncio.sleep(1)
            try:
                return await process_once()
            except:
                safe_print(f"❌ Video phase failed for {gallery_name}")
                return 0
            
async def phase3_download(ordered_galleries, mode, images_videos_together=False):
    print_banner(f"Phase 3 — Downloading {len(ordered_galleries)} galleries", "🚀")

    stats = {}  # tag → gallery → [img_count, vid_count]

    queue = asyncio.Queue()
    for entry in ordered_galleries:
        queue.put_nowait(entry)

    def norm(x):
        return x if isinstance(x, int) else 0

    async def worker(pbar):
        while True:
            try:
                link, tag, snippets, box_count, tag_total = await queue.get()
            except asyncio.CancelledError:
                return

            gallery_name = os.path.basename(urlparse(link).path.strip("/"))

            # ensure nested dict exists
            stats.setdefault(tag, {})
            stats[tag].setdefault(gallery_name, [0, 0])

            try:
                img_count = 0
                vid_count = 0

                # ----------------- IMAGES ONLY -----------------
                if mode == "images":
                    img_count = norm(
                        await download_gallery_images(link, tag, snippets, box_count, tag_total)
                    )

                # ----------------- VIDEOS ONLY -----------------
                elif mode == "videos":
                    vid_count = norm(
                        await download_gallery_videos(link, tag, snippets, box_count, tag_total)
                    )

                # ----------------- VIDEOS FIRST -----------------
                elif mode == "videos_first":
                    vid_count = norm(
                        await download_gallery_videos(link, tag, snippets, box_count, tag_total)
                    )
                    img_count = norm(
                        await download_gallery_images(link, tag, snippets, box_count, tag_total)
                    )

                # ----------------- BOTH -----------------
                else:
                    if images_videos_together:
                        # Correct parallel execution
                        img_task = download_gallery_images(
                            link, tag, snippets, box_count, tag_total
                        )
                        vid_task = download_gallery_videos(
                            link, tag, snippets, box_count, tag_total
                        )

                        img_count, vid_count = await asyncio.gather(img_task, vid_task)
                        img_count = norm(img_count)
                        vid_count = norm(vid_count)

                    else:
                        img_count = norm(
                            await download_gallery_images(link, tag, snippets, box_count, tag_total)
                        )
                        vid_count = norm(
                            await download_gallery_videos(link, tag, snippets, box_count, tag_total)
                        )

                # save the tallies
                stats[tag][gallery_name][0] += img_count
                stats[tag][gallery_name][1] += vid_count

            except Exception as e:
                safe_print(f"❌ error in download worker: {e}")

            finally:
                pbar.update(1)
                queue.task_done()

    # ----------------- Worker Pool -----------------
    with tqdm(
        total=len(ordered_galleries),
        desc="🚀 Galleries",
        position=1,
        ncols=66,
        leave=True,
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} 🚀"
    ) as t:
        workers = [
            asyncio.create_task(worker(t))
            for _ in range(min(PROCESS_GALLERIES, max(1, len(ordered_galleries))))
        ]

        await queue.join()

        for w in workers:
            w.cancel()

    return stats

# ============================================================
#  Main pipeline
# ============================================================
async def main(tags, galleries, mode, reverse_flag, simulate_flag, images_videos_flag, summary_flag):
    global semaphore_galleries
    semaphore_galleries = asyncio.Semaphore(PROCESS_GALLERIES)
    # -------- Phase 1: Tags → gallery URLs --------
    if tags:
        tag_to_galleries, all_galleries = await phase1_collect_urls(tags)
    else:
        tag_to_galleries = {"manual": galleries}
        all_galleries = set(galleries)

    if not all_galleries:
        return

    # -------- Phase 2: Scroll galleries --------
    gallery_data = await phase2_scan_galleries(tag_to_galleries)

    # De-duplicate by gallery URL (first tag wins)
    unique = {}
    for link, tag, snippets in gallery_data:
        if link not in unique:
            unique[link] = (link, tag, snippets)
    gallery_data = list(unique.values())

    # Filter out small galleries, add box_count, sort
    gallery_data = sorted(
        [
            (link, tag, snippets, len(snippets))
            for link, tag, snippets in gallery_data
            if len(snippets) > MIN_BOXES
        ],
        key=lambda x: x[3],
        reverse=reverse_flag
    )

    # Count total boxes per tag
    tag_box_totals = {}
    for _, tag, _, box_count in gallery_data:
        tag_box_totals[tag] = tag_box_totals.get(tag, 0) + box_count

    ordered_galleries = [
        (link, tag, snippets, box_count, tag_box_totals[tag])
        for link, tag, snippets, box_count in gallery_data
    ]

    # Phase 2 summary
    total_scanned = len(unique)
    total_boxes = sum(len(snippets) for _, _, snippets in unique.values())
    acceptable = len(gallery_data)
    limit = MIN_BOXES

    print_summary(
        f"Total {total_scanned} galleries",
        f"Total boxes: {total_boxes}",
        f"Min Box Limit: {limit}",
        f"Total accepted galleries: {acceptable}",
        emoji="🌐"
    )

    # -------- Phase 3: Download (unless simulate) --------
    stats = {}
    if ordered_galleries and not simulate_flag:
        if mode == "videos_first":
            # 1) Pass: videos only
            stats_v = await phase3_download(
                ordered_galleries,
                "videos",
                images_videos_together=False,
            )

            # 2) Pass: images only
            stats_i = await phase3_download(
                ordered_galleries,
                "images",
                images_videos_together=False,
            )

            # Merge stats_v and stats_i
            stats = stats_v
            for tag, galleries in stats_i.items():
                if tag not in stats:
                    stats[tag] = galleries
                    continue

                for g_name, (img, vid) in galleries.items():
                    if g_name not in stats[tag]:
                        stats[tag][g_name] = [img, vid]
                    else:
                        stats[tag][g_name][0] += img
                        stats[tag][g_name][1] += vid
        else:
            stats = await phase3_download(
                ordered_galleries,
                mode,
                images_videos_together=images_videos_flag,
            )
    elif simulate_flag:
        print_banner("Simulation Mode — Skipping Downloads", "🧪")

    # -------- Phase 4: Cleanup --------
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def fast_delete(path, index, total_targets):
        if not os.path.exists(path):
            return

        top_dirs = [
            os.path.join(path, d)
            for d in os.listdir(path)
            if os.path.isdir(os.path.join(path, d))
        ]
        folder_count = len(top_dirs)
        logical = os.cpu_count() or 32
        workers = min(16, logical)
        label = f"🧹 {index}/{total_targets} {path} ({folder_count} folders)"

        with tqdm(
            total=folder_count,
            desc=label,
            ncols=66,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} 🧹"
        ) as pbar:
            with ThreadPoolExecutor(max_workers=workers) as exe:
                futures = {exe.submit(shutil.rmtree, d, True): d for d in top_dirs}
                for _ in as_completed(futures):
                    pbar.update(1)

        try:
            shutil.rmtree(path, ignore_errors=True)
        except:
            pass

    cleanup_targets = ["__pycache__", "userdata"]
    total = len(cleanup_targets)
    print_banner("Phase 4/4 — Cleanup", "🧹")

    for i, target in enumerate(cleanup_targets, start=1):
        fast_delete(target, i, total)

    print_banner("Cleanup Complete", "✅")
    
    # -------- Optional Summary Output --------
    if summary_flag and stats:
        print_banner("Download Summary", "📦")

        # sort tags by total media
        sorted_tags = sorted(
            stats.items(),
            key=lambda kv: sum(i + v for i, v in kv[1].values()),
            reverse=True
        )

        for tag, galleries_info in sorted_tags:
            tag_total_imgs = sum(v[0] for v in galleries_info.values())
            tag_total_vids = sum(v[1] for v in galleries_info.values())

            safe_print(
                f"📦 [green]{tag[:35]:<35}[/green] | "
                f"{tag_total_imgs:>3} images, {tag_total_vids:>3} videos 📦"
            )

            # sort galleries
            sorted_galleries = sorted(
                galleries_info.items(),
                key=lambda kv: (kv[1][0] + kv[1][1]),
                reverse=True
            )

            for gallery_name, (imgs, vids) in sorted_galleries:
                safe_print(
                    f"📦  • {gallery_name[:32]:<32} | "
                    f"{imgs:>3} images, {vids:>3} videos 📦"
                )

            safe_print("📦 " + "═" * 60 + " 📦")

# ============================================================
#  Entry Point (Subcommand-Based)
# ============================================================
if __name__ == "__main__":
    ensure_settings_file()
    asyncio.run(cache_db.init_db())
    settings = load_settings()

    # ============================================================
    #  Apply settings from INI (numeric + boolean)
    # ============================================================
    PROCESS_IMAGES     = settings["PROCESS_IMAGES"]
    PROCESS_VIDEOS     = settings["PROCESS_VIDEOS"]
    PROCESS_GALLERIES  = settings["PROCESS_GALLERIES"]
    SCAN_TAGS          = settings["SCAN_TAGS"]
    SCAN_GALLERIES     = settings["SCAN_GALLERIES"]
    MIN_BOXES          = settings["MIN_BOXES"]

    # boolean defaults from INI
    ini_reverse       = settings["reverse"]
    ini_simulate      = settings["simulate"]
    ini_imagesvideos  = settings["images_videos"]
    ini_summary       = settings["summary"]
    ini_videosonly    = settings["videos_only"]
    ini_imagesonly    = settings["images_only"]
    ini_videosfirst   = settings["videos_first"]

    parser = argparse.ArgumentParser(description="Ultimate Scraper")

    # ============================================================
    #  Subcommands
    # ============================================================
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ------------------------------------------------------------
    #  SET COMMAND
    # ------------------------------------------------------------
    set_cmd = subparsers.add_parser("set", help="Modify settings.ini")

    set_cmd.add_argument("key", help="Setting key")
    set_cmd.add_argument("value", help="Value to set")

    # ------------------------------------------------------------
    #  RUN COMMAND
    # ------------------------------------------------------------
    run_cmd = subparsers.add_parser("run", help="Run the scraper")

    run_cmd.add_argument("tags", nargs="*", help="Tags to process")
    run_cmd.add_argument("-t", "--tags-file", help="Load tags from file")
    run_cmd.add_argument("-g", "--galleries", nargs="+", help="Specific gallery URLs")
    run_cmd.add_argument("-G", "--galleries-file", help="Load gallery URLs from file")

    run_cmd.add_argument("--last", nargs="?", const="all",
                         help="Use tags from last.txt (default = all)")

    # runtime boolean flags override settings.ini
    run_cmd.add_argument("-r", "--reverse", action="store_true")
    run_cmd.add_argument("-sim", "--simulate", action="store_true")
    run_cmd.add_argument("-iv", "--images-videos", action="store_true")
    run_cmd.add_argument("-s", "--summary", action="store_true")

    mode_group = run_cmd.add_mutually_exclusive_group()
    mode_group.add_argument("-v", "--videos-only", action="store_true")
    mode_group.add_argument("-i", "--images-only", action="store_true")
    mode_group.add_argument("-vf", "--videos-first", action="store_true")

    args = parser.parse_args()

    # ============================================================
    #  HANDLE `set` COMMAND
    # ============================================================
    if args.command == "set":
        key_map = {
            "images":         "process_images",
            "videos":         "process_videos",
            "galleries":      "process_galleries",
            "scan_tags":      "scan_tags",
            "scan_galleries": "scan_galleries",
            "min_boxes":      "min_boxes",
            "reverse":        "reverse",
            "simulate":       "simulate",
            "images_videos":  "images_videos",
            "summary":        "summary",
            "videos_only":    "videos_only",
            "images_only":    "images_only",
            "videos_first":   "videos_first",
        }

        k = args.key.lower()
        if k not in key_map:
            print(f"❌ Unknown setting '{args.key}'")
            sys.exit(1)

        update_setting(key_map[k], args.value)
        print(f"✅ Updated {key_map[k]} to {args.value}")
        sys.exit(0)

    # ============================================================
    #  HANDLE `run` COMMAND
    # ============================================================
    if args.command == "run":

        # ============================================================
        #  Merge runtime flags with INI defaults
        # ============================================================
        reverse_flag       = ini_reverse       or args.reverse
        simulate_flag      = ini_simulate      or args.simulate
        images_videos_flag = ini_imagesvideos  or args.images_videos

        # Summary logic: TRUE in INI means "show summary"
        # CLI -s means "disable summary"
        summary_flag       = ini_summary and not args.summary

        videos_only_flag   = ini_videosonly    or args.videos_only
        images_only_flag   = ini_imagesonly    or args.images_only
        videos_first_flag  = ini_videosfirst   or args.videos_first

        # ============================================================
        #  Determine mode using merged flags
        # ============================================================
        if videos_only_flag:
            mode = "videos"
        elif images_only_flag:
            mode = "images"
        elif videos_first_flag:
            mode = "videos_first"
        else:
            mode = "both"

        # ============================================================
        #  Collect tags & galleries
        # ============================================================
        tags = args.tags or []
        galleries = args.galleries or []

        if args.tags_file:
            with open(args.tags_file, "r", encoding="utf-8") as f:
                tags.extend(line.strip() for line in f if line.strip())

        if args.galleries_file:
            with open(args.galleries_file, "r", encoding="utf-8") as f:
                galleries.extend(line.strip() for line in f if line.strip())

        # ---------------- LAST FROM DB ----------------
        import common.cache_db as cache_db

        def get_last_tags_from_db(limit):
            async def _inner():
                return await cache_db.get_last(limit)
            return asyncio.run(_inner())


        if args.last:
            if args.last == "all":
                tags = get_last_tags_from_db(None)
                print(f"📂 Loaded ALL {len(tags)} tags from database history.")
            else:
                try:
                    n = int(args.last)
                    tags = get_last_tags_from_db(n)
                    print(f"📂 Loaded last {n} tags from DB.")
                except:
                    print("❌ Invalid --last value")
                    sys.exit(1)
        else:
            # no --last flag, use provided tags source
            pass

        # Cleanup + sorting
        if tags:
            tags = sorted({t.lower() for t in tags})

        if not tags and not galleries:
            print("❌ Need at least 1 tag or gallery.")
            sys.exit(1)

        # ============================================================
        #  Print Active Flags Summary
        # ============================================================
        summary_lines = []

        summary_lines.append(f"TheFap Gallery Downloader")
        if simulate_flag:      summary_lines.append("Simulation Mode Enabled")
        if images_videos_flag: summary_lines.append("Images + Videos Together")
        if not summary_flag:   summary_lines.append("Summary Disabled")
        if reverse_flag:       summary_lines.append("Reverse Sorting Enabled")
        if args.tags_file:     summary_lines.append(f"Tags File: {args.tags_file}")
        if args.galleries_file:summary_lines.append(f"Gallery File: {args.galleries_file}")
        if args.galleries:     summary_lines.append(f"Manual Galleries: {len(args.galleries)}")
        if args.last:          summary_lines.append(f"Using Last: {args.last}")

        print_summary(*summary_lines, emoji="🧭")

        # ============================================================
        #  Run Scraper
        # ============================================================
        try:
            asyncio.run(main(
                tags,
                galleries,
                mode,
                reverse_flag,
                simulate_flag,
                False,
                summary_flag
            ))
        except KeyboardInterrupt:
            _sigint_handler(None, None)
