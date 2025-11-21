# ============================================================
#  FILE: scraper/common/phase1/scan_tags.py
#  Phase 1 — Tag → Gallery Link Fetcher
# ============================================================

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from tqdm import tqdm

from scraper.common import cache_db
from scraper.common.common import BASE_DOMAIN, BASE_URL, safe_print
import scraper.common.settings as settings  # <-- FIXED


# ============================================================
#  Tag → Gallery Link Fetcher (cached)
# ============================================================
async def get_links(session, tag: str):
    cached_links = await cache_db.load_tag(tag, settings.DAYS_CACHE_VALID)
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
        await cache_db.save_tag(tag, links, settings.DAYS_CACHE_VALID)

    return links


# ============================================================
#  Phase 1: Collect gallery URLs for all tags
# ============================================================
async def phase1_collect_urls(tags):
    from scraper.main import print_banner  # lazy import to avoid circular

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
            ncols=66,
            leave=True,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} 🔍"
        ) as pbar:

            workers = [
                asyncio.create_task(worker(pbar))
                for _ in range(min(settings.SCAN_TAGS_CONC, max(1, len(tags))))
            ]

            await queue.join()

            for w in workers:
                w.cancel()

    return tag_to_galleries, list(all_galleries)
