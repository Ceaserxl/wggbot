# ============================================================
#  FILE: scraper/common/phase1/scan_tags.py
#  Phase 1A — Tag → Gallery URL Collector (cached)
# ============================================================

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from tqdm import tqdm
from pathlib import Path

from scraper.common import cache_db
from scraper.common.common import BASE_DOMAIN, BASE_URL, safe_print
import scraper.common.settings as settings


# ============================================================
#  DEBUG SYSTEM
# ============================================================
debug = True

PHASE1_DIR = Path(__file__).resolve().parent
PHASE1_DEBUG_FILE = PHASE1_DIR / "phase1_debug.txt"


def dlog(*args):
    """Write to phase1A_debug.txt if debug=True."""
    if not debug:
        return
    try:
        with open(PHASE1_DEBUG_FILE, "a", encoding="utf-8") as f:
            f.write(" ".join(str(a) for a in args) + "\n")
    except Exception as e:
        print("Phase1A debug log error:", e)


# Clear log on each run
try:
    PHASE1_DEBUG_FILE.unlink()
except FileNotFoundError:
    pass


# ============================================================
#  Fetch gallery URLs for a single tag (with DB cache)
# ============================================================
async def get_links(session, tag: str):
    dlog(f"[get_links] START tag={tag}")

    # Check DB
    cached_links = await cache_db.load_tag(tag, settings.DAYS_CACHE_VALID)

    if cached_links is not None:
        dlog(f"[get_links] tag={tag} → CACHED {len(cached_links)} links")
        return cached_links

    # Fetch live page
    url = BASE_URL.format(tag)
    dlog(f"[get_links] FETCH {url}")

    async with session.get(url, timeout=60) as r:
        html = await r.text()

    dlog(f"[get_links] tag={tag} HTML size={len(html)} bytes")

    soup = BeautifulSoup(html, "html.parser")
    boxes = soup.find_all("div", class_="bg-red-400")

    dlog(f"[get_links] tag={tag} found {len(boxes)} boxes")

    links = []
    for box in boxes:
        a = box.find("a", href=True)
        if not a:
            dlog(f"[get_links] tag={tag} SKIP box (no <a>)")
            continue

        href = a["href"]
        dlog(f"[get_links] tag={tag} raw href={href}")

        if href.startswith("/"):
            href = BASE_DOMAIN + href
            dlog(f"[get_links] tag={tag} normalized href={href}")

        links.append(href)

    # Save
    if links:
        dlog(f"[get_links] tag={tag} SAVE {len(links)} links")
        await cache_db.save_tag(tag, links, settings.DAYS_CACHE_VALID)
    else:
        dlog(f"[get_links] tag={tag} NO LINKS FOUND")

    return links


# ============================================================
#  Phase 1A — Collect gallery URLs for all tags
# ============================================================
async def phase1A_collect_urls(tags):
    from scraper.main import print_banner  # avoid circular imports

    print_banner("Phase 1 — Collecting URLs", "🔍")

    dlog(f"[phase1A_collect_urls] START tags={tags}")

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

                dlog(f"[worker] START tag={tag}")

                try:
                    links = await get_links(session, tag)
                    tag_to_galleries[tag] = links
                    all_galleries.update(links)
                    dlog(f"[worker] tag={tag} → {len(links)} links")
                except Exception as e:
                    safe_print(f"❌ Failed tag {tag}: {e}")
                    dlog(f"[worker] ERROR tag={tag}: {e}")
                finally:
                    pbar.update(1)
                    queue.task_done()
        tags_total = len(tags)
        with tqdm(
            total=tags_total,
            desc=f"🔍 Scanning {tags_total} Tags",
            ncols=66,
            leave=True,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} 🔍"
        ) as pbar:

            workers = [
                asyncio.create_task(worker(pbar))
                for _ in range(min(settings.SCAN_TAGS_CONC, len(tags) or 1))
            ]

            await queue.join()

            for w in workers:
                w.cancel()

    dlog(f"[phase1A_collect_urls] DONE. Unique galleries={len(all_galleries)}")

    return tag_to_galleries, list(all_galleries)
