# ============================================================
#  FILE: scraper/common/phase3/get_media_db.py
#  Phase 3 — Extract media URLs from DB-stored HTML
# ============================================================

import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import aiosqlite

from scraper.common.common import BASE_DOMAIN
from scraper.common.cache_db import DB_PATH


# ============================================================
#  Image URL Extraction (from DB HTML)
# ============================================================
async def get_gallery_images(gallery_url: str) -> list[str]:
    """
    Returns a list of clean image URLs extracted from DB-stored HTML.
    Only reads from gallery_items WHERE kind='image'.
    """

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT html FROM gallery_items "
            "WHERE gallery=? AND kind='image' "
            "ORDER BY idx ASC",
            (gallery_url,)
        )
        rows = await cur.fetchall()

    if not rows:
        return []

    urls = set()

    for (html,) in rows:
        soup = BeautifulSoup(html, "html.parser")

        img = soup.find("img")
        if not img:
            continue

        src = img.get("src")
        if not src:
            continue

        # Normalize protocol-relative URLs
        if src.startswith("//"):
            src = "https:" + src

        # Site-relative → make absolute
        elif not src.startswith("http"):
            src = urljoin(BASE_DOMAIN, src)

        # Only accept valid image extensions
        if re.search(
            r"\.(jpg|jpeg|png|gif|webp|avif)(\?.*)?$",
            src,
            re.IGNORECASE
        ):
            urls.add(src)

    return list(urls)


# ============================================================
#  Video Page URL Extraction (from DB HTML)
# ============================================================
async def get_gallery_video_pages(gallery_url: str) -> list[str]:
    """
    Returns the video-page URLs extracted from DB-stored HTML.
    The <a href="..."> in the box links to the separate page that
    contains the dood/stream server buttons.
    """

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT html FROM gallery_items "
            "WHERE gallery=? AND kind='video' "
            "ORDER BY idx ASC",
            (gallery_url,)
        )
        rows = await cur.fetchall()

    if not rows:
        return []

    urls = []

    for (html,) in rows:
        soup = BeautifulSoup(html, "html.parser")

        # Find the <a> tag wrapping the play icon
        a = soup.find("a", href=True)
        if not a:
            continue

        href = a["href"]
        if href.startswith("/"):
            href = BASE_DOMAIN + href

        urls.append(href)

    return urls
