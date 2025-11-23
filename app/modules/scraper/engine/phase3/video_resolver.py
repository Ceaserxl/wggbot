# ============================================================
#  resolve_video_page.py
#  Phase 3 — Resolve a video page → final downloadable URL
# ============================================================

import re
import base64
from urllib.parse import urlparse, parse_qs

from scraper.common.common import decode_file_param

VIDEO_EXT_PATTERN = (
    r"\.(mp4|webm|mkv|mov|avi|flv|m4v|wmv|ts|mpeg|mpg)([/?#]|$)"
)


# ============================================================
# Extract server URLs from the video page
# ============================================================
async def extract_video_servers(page):
    servers = []

    # ------------------------------------------------------------
    # 1) Base64-encoded <button class="sv-change" value="...">
    # ------------------------------------------------------------
    buttons = await page.query_selector_all("button.sv-change")
    for btn in buttons:
        val = await btn.get_attribute("value")
        if not val:
            continue

        try:
            decoded = base64.b64decode(val).decode(errors="ignore")
            qs = parse_qs(urlparse(decoded).query)
            if "file" in qs:
                real = decode_file_param(qs["file"][0])
                if real:
                    servers.append(real)
        except:
            continue

    # ------------------------------------------------------------
    # 2) Regex extract raw video links from HTML
    # ------------------------------------------------------------
    html = await page.content()

    matches = re.findall(
        r"(https?://[^\s\"']+" + VIDEO_EXT_PATTERN + ")",
        html, re.IGNORECASE
    )

    for item in matches:
        if isinstance(item, tuple):
            servers.append(item[0])
        else:
            servers.append(item)

    return servers


# ============================================================
# Resolve dood / embed providers → real direct video URL
# ============================================================
async def resolve_dood_link(context, url):
    try:
        page = await context.new_page()
        page.set_default_timeout(15000)

        try:
            await page.goto(url, timeout=15000)
        except:
            await page.close()
            return None

        # Try <video> / <source> directly
        direct = (
            await page.get_attribute("video", "src") or
            await page.get_attribute("source", "src")
        )
        if direct:
            await page.close()
            return direct

        # Fallback regex
        html = await page.content()
        m = re.search(r"https?://[^\s\"']+" + VIDEO_EXT_PATTERN, html)
        await page.close()
        return m.group(0) if m else None

    except:
        return None


# ============================================================
# MASTER: resolve a video-page URL → final direct download URL
# ============================================================
async def resolve_video_page(context, video_page_url):
    """
    Loads a video page, extracts server links, resolves each,
    returns the first valid direct-video URL.
    """

    page = await context.new_page()
    page.set_default_timeout(20000)

    try:
        await page.goto(video_page_url, timeout=20000)
    except:
        await page.close()
        return None

    # Extract potential servers
    servers = await extract_video_servers(page)
    await page.close()

    if not servers:
        return None

    # ------------------------------------------------------------
    # Try each server in order
    # ------------------------------------------------------------
    for server in servers:

        # 1) Already a direct video link?
        if re.search(VIDEO_EXT_PATTERN, server, re.IGNORECASE):
            return server

        # 2) Try dood/embeds
        if any(x in server for x in ["dood.", "embed-", "bigwarp.io", "/embed/"]):
            resolved = await resolve_dood_link(context, server)
            if resolved and re.search(VIDEO_EXT_PATTERN, resolved, re.IGNORECASE):
                return resolved

    return None
