# ============================================================
#  FILE: scraper/common/phase1/scan_galleries.py
#  Phase 1B — Scroll & Capture gallery boxes (outerHTML cache)
# ============================================================

import asyncio
import os
from urllib.parse import urlparse
from tqdm import tqdm
from pathlib import Path

from scraper.common import cache_db
from scraper.common.common import (
    safe_print,
    print_banner,
    launch_chromium,
    stop_event
)
import scraper.common.settings as settings


# ============================================================
#  DEBUG SYSTEM — phase1_debug.txt (same file as scan_tags.py)
# ============================================================
debug = True

PHASE1_DIR = Path(__file__).resolve().parent
PHASE1_DEBUG_FILE = PHASE1_DIR / "phase1_debug.txt"


def dlog(*args):
    """Write text into phase1_debug.txt if debug=True."""
    if not debug:
        return
    try:
        with open(PHASE1_DEBUG_FILE, "a", encoding="utf-8") as f:
            f.write(" ".join(str(a) for a in args) + "\n")
    except Exception as e:
        print("Phase1 debug log ERROR:", e)


# ============================================================
#  Scroll gallery until no more dynamic boxes appear
# ============================================================
async def scroll_gallery(context, url, delay=1000):
    """
    Scrolls until dynamic content stops loading.

    Returns:
        page, boxes[]
    """
    dlog(f"[scroll_gallery] OPEN {url}")

    page = await context.new_page()
    await page.goto(url, timeout=180000)

    last_count = 0
    same_rounds = 0

    while True:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(delay)

        boxes = await page.query_selector_all("#content > div")
        count = len(boxes)

        dlog(f"[scroll_gallery] box_count={count} last={last_count} same_rounds={same_rounds}")

        # no new boxes → stable twice → done
        if count == last_count:
            same_rounds += 1
            if same_rounds >= 2:
                dlog("[scroll_gallery] DONE (no new boxes)")
                break
        else:
            same_rounds = 0
            last_count = count

        if stop_event.is_set():
            dlog("[scroll_gallery] CANCELLED (stop_event)")
            raise asyncio.CancelledError

    return page, boxes


# ============================================================
#  Scrape gallery → return raw outerHTML boxes
# ============================================================
async def scrape_gallery_boxes(link, tag):
    """
    Returns: (link, tag, [outerHTML boxes])
    """

    dlog(f"\n=== scrape_gallery_boxes START {link} tag={tag} ===")

    # ----- Try cache first -----
    cached = await cache_db.load_gallery(link, settings.DAYS_CACHE_VALID)
    if cached is not None:
        dlog(f"[scrape_gallery_boxes] USING CACHE {link} ({len(cached)} boxes)")
        return (link, tag, cached)

    gallery_name = os.path.basename(urlparse(link).path.strip("/"))

    try:
        dlog(f"[scrape_gallery_boxes] launch browser for {gallery_name}")

        p, context = await launch_chromium(
            f"userdata/userdata_{gallery_name}",
            headless=True
        )

        page, boxes = await scroll_gallery(context, link)
        dlog(f"[scrape_gallery_boxes] {gallery_name} loaded {len(boxes)} boxes")

        # Extract raw HTML
        snippets = []
        for i, b in enumerate(boxes, start=1):
            html = await b.evaluate("el => el.outerHTML")
            snippets.append((i, html))   # STORE REAL INDEX
            dlog(f"[scrape_gallery_boxes][box {i}] LEN={len(html)}")

        # Cleanup
        await page.close()
        await context.close()
        await p.stop()

        # Save to cache
        if snippets:
            dlog(f"[scrape_gallery_boxes] SAVE {len(snippets)} boxes for {gallery_name}")
            await cache_db.save_gallery(
                link,
                tag,
                snippets,
                settings.DAYS_CACHE_VALID
            )

        dlog(f"=== scrape_gallery_boxes END {link} ===\n")
        return (link, tag, snippets)

    except asyncio.CancelledError:
        dlog(f"[scrape_gallery_boxes] CANCELLED {link}")
        raise

    except Exception as e:
        safe_print(f"❌ Failed to scrape {gallery_name}: {e}")
        dlog(f"[scrape_gallery_boxes] ERROR {gallery_name}: {e}")
        return (link, tag, [])


# ============================================================
#  Phase 1B — Scan all galleries for all tags
# ============================================================
async def phase1B_scan_galleries(tag_to_galleries):
    """
    Input:  { tag: [gallery URLs] }
    Output: list[(link, tag, [outerHTML])]
    """
    all_tasks = [
        (link, tag)
        for tag, glist in tag_to_galleries.items()
        for link in glist
    ]

    """ print_banner(f"Phase 1B — Scanning {len(all_tasks)} Galleries", "🌐") """

    dlog(f"[phase1B_scan_galleries] START total={len(all_tasks)}")

    queue = asyncio.Queue()
    results = []

    for link, tag in all_tasks:
        queue.put_nowait((link, tag))

    # worker
    async def worker(pbar):
        while True:
            try:
                link, tag = await queue.get()
            except asyncio.CancelledError:
                return

            dlog(f"[phase1B_worker] START {link} tag={tag}")

            try:
                data = await scrape_gallery_boxes(link, tag)
                if data[2]:  # has snippets
                    results.append(data)
                    dlog(f"[phase1B_worker] SAVED {link} with {len(data[2])} boxes")
                else:
                    dlog(f"[phase1B_worker] EMPTY {link}")
            except Exception as e:
                safe_print(f"❌ failed gallery {link}: {e}")
                dlog(f"[phase1B_worker] ERROR {link}: {e}")
            finally:
                pbar.update(1)
                queue.task_done()

    # run pool
    gal_total = len(all_tasks)
    with tqdm(
        total=len(all_tasks),
        desc=f"🌐 Scanning {gal_total} Galleries",
        ncols=66,
        leave=True,
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} 🌐"
    ) as pbar:

        workers = [
            asyncio.create_task(worker(pbar))
            for _ in range(min(settings.SCAN_GALLS_CONC, max(1, len(all_tasks))))
        ]

        await queue.join()

        for w in workers:
            w.cancel()

    dlog(f"[phase1B_scan_galleries] END results={len(results)}\n")
    return results
