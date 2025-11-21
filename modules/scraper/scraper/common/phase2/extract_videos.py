# ============================================================
#  FILE: scraper/common/phase2/extract_videos.py
#  Phase 2B — Extract video PAGE URLs from HTML snippets
# ============================================================

import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from scraper.common.common import BASE_DOMAIN


# ============================================================
#  Extract video PAGE links from gallery HTML snippets
# ============================================================
def extract_video_pages_from_snippets(snippets: list[str]) -> list[str]:
    """
    Input:  list of raw HTML snippets saved during Phase 1B.
    Output: list of ABSOLUTE URLs to video PAGE links (NOT server links).
    
    Rules:
      - A video box is any snippet containing: <img src="...icon-play.svg">
      - Boxes may contain BOTH a real image and the play icon → still a video.
      - Extract the <a href="..."> that wraps the box.
    """

    video_pages = set()

    for html in snippets:
        soup = BeautifulSoup(html, "html.parser")

        # ------------------------------------------------------------
        # Detect video indicator anywhere inside this snippet
        # ------------------------------------------------------------
        has_play_icon = soup.find("img", src=lambda s: s and "icon-play.svg" in s)
        if not has_play_icon:
            continue

        # ------------------------------------------------------------
        # The video PAGE is always the wrapping <a href="...">
        # ------------------------------------------------------------
        a = soup.find("a", href=True)
        if not a:
            continue

        href = a["href"].strip()
        if not href:
            continue

        # ------------------------------------------------------------
        # Normalize into full URL
        # ------------------------------------------------------------
        if href.startswith("//"):
            href = "https:" + href

        elif href.startswith("/"):
            href = BASE_DOMAIN + href

        elif not href.startswith("http"):
            href = urljoin(BASE_DOMAIN, href)

        video_pages.add(href)

    return list(video_pages)
