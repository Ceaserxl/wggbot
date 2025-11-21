# ============================================================
#  scan_galleries.py — Phase 2 (Scroll + Extract Gallery Boxes)
#  Location: scraper/common/phase1/scan_galleries.py
# ============================================================

import asyncio
import os
from urllib.parse import urlparse
from tqdm import tqdm

# -----------------------------
# Correct project imports
# -----------------------------
from scraper.common import cache_db
from scraper.common.common import (
    BASE_DOMAIN,
    safe_print,
    print_banner,
    launch_chromium,
)
from scraper.common.settings import (
    CACHE_DAYS,
    SCAN_GALLERIES_CONC,
)


# ============================================================
#  Scroll gallery until all content is loaded
# ============================================================
async def scroll_gallery(context, url, delay=1000):
    page = await context.new_page()
    await page.goto(url, timeout=180000)

    last_count = 0
    same_rounds = 0

    while True:
        # Scroll to bottom
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(delay)

        boxes = await page.query_selector_all("#content > div")
        count = len(boxes)

        # Stop after two rounds with no new results
        if count == last_count:
            same_rounds += 1
            if same_rounds >= 2:
                break
        else:
            same_rounds = 0
            last_count = count

    return page, boxes


# ============================================================
#  Scrape a single gallery → return list of snippet HTML
# ============================================================
async def scrape_gallery_boxes(link, tag):
    # Try load from cache
    cached = await cache_db.load_gallery(link, CACHE_DAYS)
    if cached is not None:
        return (link, tag, cached)

    gallery_name = os.path.basename(urlparse(link).path.strip("/"))

    try:
        # Launch Chromium
        p, context = await launch_chromium(f"userdata/gallery_{gallery_name}", headless=True)

        page, boxes = await scroll_gallery(context, link)

        # Extract HTML snippet for each box
        snippets = [await b.evaluate("el => el.outerHTML") for b in boxes]

        await page.close()
        await context.close()
        await p.stop()

        # Save cache
        if snippets:
            await cache_db.save_gallery(link, tag, snippets, CACHE_DAYS)

        return (link, tag, snippets)

    except asyncio.CancelledError:
        raise

    except Exception as e:
        safe_print(f"❌ Failed to scrape gallery {gallery_name}: {e}")
        return (link, tag, [])


# ============================================================
#  Phase 2 — Scan ALL galleries discovered in Phase 1
# ============================================================
async def phase2_scan_galleries(tag_to_galleries):
    # Flatten work list
    all_tasks = [
        (link, tag)
        for tag, glist in tag_to_galleries.items()
        for link in glist
    ]

    print_banner(f"Phase 2 — Scanning {len(all_tasks)} Galleries", "🌐")

    queue = asyncio.Queue()
    for item in all_tasks:
        queue.put_nowait(item)

    results = []

    async def worker(pbar):
        while True:
            try:
                link, tag = await queue.get()
            except asyncio.CancelledError:
                return

            try:
                data = await scrape_gallery_boxes(link, tag)
                if data[2]:  # Has snippets
                    results.append(data)
            except Exception as e:
                safe_print(f"❌ Gallery failed {link}: {e}")
            finally:
                pbar.update(1)
                queue.task_done()

    # Progress bar
    with tqdm(
        total=len(all_tasks),
        desc="🌐 Scanning Galleries",
        ncols=66,
        leave=True,
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} 🌐"
    ) as pbar:

        workers = [
            asyncio.create_task(worker(pbar))
            for _ in range(min(SCAN_GALLERIES_CONC, max(1, len(all_tasks))))
        ]

        await queue.join()

        for w in workers:
            w.cancel()

    return results
