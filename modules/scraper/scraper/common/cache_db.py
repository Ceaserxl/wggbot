# ============================================================
#  cache_db.py — Async SQLite Cache Layer (FIXED FOR TUPLES)
# ============================================================

import os
import time
import aiosqlite
from pathlib import Path
import re

debug = True

def debug_log(*args):
    if not debug:
        return
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(CACHE_DIR / "debug_cache.txt", "a", encoding="utf-8") as f:
            f.write(" ".join(str(a) for a in args) + "\n")
    except Exception as e:
        print("Debug log error:", e)

BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR.parent / "cache"
DB_PATH = CACHE_DIR / "cache.db"

CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS tag_gallery (
    tag     TEXT,
    gallery TEXT
);

CREATE INDEX IF NOT EXISTS idx_tag_gallery_tag
    ON tag_gallery(tag);

CREATE INDEX IF NOT EXISTS idx_tag_gallery_gallery
    ON tag_gallery(gallery);

CREATE TABLE IF NOT EXISTS galleries (
    gallery       TEXT PRIMARY KEY,
    raw_box_count INTEGER,
    box_count     INTEGER,
    img_count     INTEGER,
    vid_count     INTEGER,
    scanned_at    INTEGER
);

CREATE TABLE IF NOT EXISTS gallery_items (
    gallery TEXT,
    idx     INTEGER,
    kind    TEXT,
    html    TEXT,
    PRIMARY KEY (gallery, idx, kind)
);

CREATE INDEX IF NOT EXISTS idx_gallery_items_gallery_kind
    ON gallery_items(gallery, kind);

CREATE TABLE IF NOT EXISTS history_tags (
    tag      TEXT PRIMARY KEY,
    added_at INTEGER
);
"""

async def init_db():
    CACHE_DIR.mkdir(exist_ok=True, parents=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(CREATE_TABLES)
        await db.commit()


# ============================================================
#  TAG CACHE (unchanged)
# ============================================================

async def load_tag(tag: str, ttl_days: int | None = None):
    tag = tag.lower()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT gallery FROM tag_gallery WHERE tag=?", (tag,))
        rows = await cur.fetchall()
    return [r[0] for r in rows] if rows else None


async def save_tag(tag: str, links: list[str], ttl_days: int | None = None):
    tag = tag.lower()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM tag_gallery WHERE tag=?", (tag,))
        for gallery in links:
            await db.execute(
                "INSERT INTO tag_gallery (tag, gallery) VALUES (?, ?)",
                (tag, gallery),
            )
        await db.commit()


# ============================================================
#  LOAD GALLERY
# ============================================================

async def _is_gallery_fresh(db, gallery: str, ttl_days: int | None):
    if ttl_days is None:
        return True

    cur = await db.execute(
        "SELECT scanned_at FROM galleries WHERE gallery=?", (gallery,)
    )
    row = await cur.fetchone()
    if not row:
        return False

    scanned_at = row[0]
    return (time.time() - scanned_at) <= ttl_days * 86400


async def load_gallery(url: str, ttl_days: int | None = None):
    async with aiosqlite.connect(DB_PATH) as db:

        if not await _is_gallery_fresh(db, url, ttl_days):
            return None

        cur = await db.execute(
            "SELECT idx, html FROM gallery_items WHERE gallery=? ORDER BY idx ASC",
            (url,),
        )
        rows = await cur.fetchall()

    if not rows:
        return None

    # RETURN FORMAT: [(idx, html), ...]
    return [(r[0], r[1]) for r in rows]


# ============================================================
#  SAVE GALLERY — FIXED
# ============================================================

async def save_gallery(url: str, tag: str, snippets: list, ttl_days: int | None = None):
    """
    snippets MUST be in format:  [(idx, html), ...]
    """
    now = int(time.time())

    # Ensure proper format
    fixed = []
    for i, item in enumerate(snippets, start=1):
        if isinstance(item, tuple):
            fixed.append(item)
        else:
            fixed.append((i, item))

    raw_box_count = len(fixed)

    IMG_TAG = re.compile(r"<img[^>]+(?:src|data-src)=", re.IGNORECASE)

    items = []
    img_count = 0
    vid_count = 0

    for idx, html in fixed:
        lower = html.lower()

        has_video = ("icon-play.svg" in lower)
        has_image = bool(IMG_TAG.search(lower))

        if has_image:
            img_count += 1
            items.append((idx, "image", html))

        if has_video:
            vid_count += 1
            items.append((idx, "video", html))

    box_count = len(items)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM gallery_items WHERE gallery=?", (url,))

        for idx, kind, html in items:
            await db.execute(
                """
                INSERT OR REPLACE INTO gallery_items (gallery, idx, kind, html)
                VALUES (?, ?, ?, ?)
                """,
                (url, idx, kind, html),
            )

        await db.execute(
            """
            INSERT OR REPLACE INTO galleries
            (gallery, raw_box_count, box_count, img_count, vid_count, scanned_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (url, raw_box_count, box_count, img_count, vid_count, now),
        )

        await db.commit()


# ============================================================
#  GET IMAGES / VIDEOS — Return (idx, html)
# ============================================================

async def get_gallery_images(url: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT idx, html FROM gallery_items
            WHERE gallery=? AND kind='image'
            ORDER BY idx ASC
            """,
            (url,),
        )
        rows = await cur.fetchall()

    return [(r[0], r[1]) for r in rows]


async def get_gallery_video_pages(url: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT idx, html FROM gallery_items
            WHERE gallery=? AND kind='video'
            ORDER BY idx ASC
            """,
            (url,),
        )
        rows = await cur.fetchall()

    return [(r[0], r[1]) for r in rows]

# ============================================================
#  HISTORY TAGS — Save + Get Last Tags
# ============================================================

async def save_last_tag(tag: str):
    """Stores the tag in the history table with timestamp."""
    tag = tag.lower()
    now = int(time.time())

    async with aiosqlite.connect(DB_PATH) as db:
        # Replace older entry for same tag
        await db.execute(
            """
            INSERT OR REPLACE INTO history_tags (tag, added_at)
            VALUES (?, ?)
            """,
            (tag, now),
        )
        await db.commit()


async def get_last(n: int | None = None):
    async with aiosqlite.connect(DB_PATH) as db:
        if n is None:
            cur = await db.execute(
                "SELECT tag FROM history_tags ORDER BY added_at DESC"
            )
        else:
            cur = await db.execute(
                "SELECT tag FROM history_tags ORDER BY added_at DESC LIMIT ?",
                (n,),
            )
        rows = await cur.fetchall()

    return [r[0] for r in rows] if rows else []