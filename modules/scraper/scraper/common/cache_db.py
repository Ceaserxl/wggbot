# ============================================================
#  cache_db.py — Async SQLite Cache Layer
#  Location: scraper/common/cache_db.py
# ============================================================

import os
import time
import aiosqlite
from pathlib import Path
import re

# ============================================================
#  DEBUG MODE
# ============================================================
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


# ------------------------------------------------------------
#  DB path
# ------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR.parent / "cache"
DB_PATH = CACHE_DIR / "cache.db"

# ------------------------------------------------------------
#  TABLE DEFINITIONS
# ------------------------------------------------------------
CREATE_TABLES = """
-- Tag → Gallery mappings
CREATE TABLE IF NOT EXISTS tag_gallery (
    tag     TEXT,
    gallery TEXT
);

CREATE INDEX IF NOT EXISTS idx_tag_gallery_tag
    ON tag_gallery(tag);

CREATE INDEX IF NOT EXISTS idx_tag_gallery_gallery
    ON tag_gallery(gallery);

-- Gallery metadata
CREATE TABLE IF NOT EXISTS galleries (
    gallery       TEXT PRIMARY KEY,
    raw_box_count INTEGER,
    box_count     INTEGER,
    img_count     INTEGER,
    vid_count     INTEGER,
    scanned_at    INTEGER
);

-- All gallery items (image OR video)
CREATE TABLE IF NOT EXISTS gallery_items (
    gallery TEXT,
    idx     INTEGER,
    kind    TEXT,
    html    TEXT,
    PRIMARY KEY (gallery, idx, kind)
);

CREATE INDEX IF NOT EXISTS idx_gallery_items_gallery_kind
    ON gallery_items(gallery, kind);

-- Tag history
CREATE TABLE IF NOT EXISTS history_tags (
    tag      TEXT PRIMARY KEY,
    added_at INTEGER
);
"""


# ============================================================
#  INIT
# ============================================================
async def init_db():
    CACHE_DIR.mkdir(exist_ok=True, parents=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(CREATE_TABLES)
        await db.commit()


# ============================================================
#  TAG CACHE
# ============================================================
async def load_tag(tag: str, ttl_days: int | None = None):
    tag = tag.lower()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT gallery FROM tag_gallery WHERE tag=?", (tag,))
        rows = await cur.fetchall()

    debug_log("[load_tag]", tag, "→", len(rows), "rows")
    return [r[0] for r in rows] if rows else None


async def save_tag(tag: str, links: list[str], ttl_days: int | None = None):
    tag = tag.lower()
    debug_log("[save_tag]", tag, "links:", links)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM tag_gallery WHERE tag=?", (tag,))
        for gallery in links:
            await db.execute(
                "INSERT INTO tag_gallery (tag, gallery) VALUES (?, ?)",
                (tag, gallery),
            )
        await db.commit()


# ============================================================
#  TAG HISTORY
# ============================================================
async def add_tags(tags: list[str]):
    now = int(time.time())
    debug_log("[add_tags]", tags)

    async with aiosqlite.connect(DB_PATH) as db:
        for t in tags:
            await db.execute(
                "REPLACE INTO history_tags (tag, added_at) VALUES (?, ?)",
                (t.lower(), now),
            )
        await db.commit()


async def get_last(n: int | None = None):
    async with aiosqlite.connect(DB_PATH) as db:
        if n is None:
            cur = await db.execute("SELECT tag FROM history_tags ORDER BY added_at ASC")
        else:
            cur = await db.execute(
                "SELECT tag FROM history_tags ORDER BY added_at DESC LIMIT ?",
                (n,),
            )
        rows = await cur.fetchall()

    debug_log("[get_last]", "n=", n, "rows=", rows)
    return [r[0] for r in rows]


# ============================================================
#  GALLERY CACHE
# ============================================================
async def _is_gallery_fresh(db, gallery: str, ttl_days: int | None):
    if ttl_days is None:
        return True

    cur = await db.execute(
        "SELECT scanned_at FROM galleries WHERE gallery=?", (gallery,)
    )
    row = await cur.fetchone()

    if not row:
        debug_log("[fresh?]", gallery, "→ NO METADATA")
        return False

    scanned_at = row[0]
    age_ok = (time.time() - scanned_at) <= ttl_days * 86400

    debug_log("[fresh?]", gallery, "age_ok=", age_ok)
    return age_ok


async def get_gallery_metadata(url: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT raw_box_count, box_count, img_count, vid_count, scanned_at
            FROM galleries
            WHERE gallery=?
            """,
            (url,),
        )
        row = await cur.fetchone()

    debug_log("[get_gallery_metadata]", url, "→", row)
    if not row:
        return None

    return {
        "raw_box_count": row[0],
        "box_count": row[1],
        "img_count": row[2],
        "vid_count": row[3],
        "scanned_at": row[4],
    }


async def load_gallery(url: str, ttl_days: int | None = None):
    async with aiosqlite.connect(DB_PATH) as db:

        if not await _is_gallery_fresh(db, url, ttl_days):
            debug_log("[load_gallery]", url, "→ STALE")
            return None

        cur = await db.execute(
            "SELECT html FROM gallery_items WHERE gallery=? ORDER BY idx ASC",
            (url,),
        )
        rows = await cur.fetchall()

    debug_log("[load_gallery]", url, "→", len(rows), "snippets")
    return [r[0] for r in rows] if rows else None


# ============================================================
#  SAVE GALLERY (WITH DEBUG)
# ============================================================
async def save_gallery(url: str, tag: str, snippets: list[str], ttl_days: int | None = None):
    now = int(time.time())
    raw_box_count = len(snippets)

    debug_log("\n==============================")
    debug_log("[save_gallery BEGIN]", url)
    debug_log("Raw boxes:", raw_box_count)

    items = []
    img_count = 0
    vid_count = 0

    IMG_TAG = re.compile(r"<img[^>]+(?:src|data-src)=", re.IGNORECASE)

    for idx, html in enumerate(snippets, start=1):
        lower = html.lower()
        has_video = ("icon-play.svg" in lower)
        has_image = bool(IMG_TAG.search(html))

        debug_log(f"[box {idx}] has_image={has_image} has_video={has_video}")
        debug_log(f"[box {idx} HTML]", html)

        if has_image:
            img_count += 1
            items.append((idx, "image", html))

        if has_video:
            vid_count += 1
            items.append((idx, "video", html))

    box_count = len(items)

    debug_log("img_count=", img_count, "vid_count=", vid_count, "box_count=", box_count)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM gallery_items WHERE gallery=?", (url,))

        for idx, kind, html in items:
            debug_log("[DB INSERT]", idx, kind)
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

    debug_log("[save_gallery END]", url)
    debug_log("==============================\n")


# ============================================================
#  PHASE 3 – IMAGES
# ============================================================
async def get_gallery_images(url: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT html FROM gallery_items
            WHERE gallery=? AND kind='image'
            ORDER BY idx ASC
            """,
            (url,),
        )
        rows = await cur.fetchall()

    debug_log("[get_gallery_images]", url, "→", len(rows))
    return [r[0] for r in rows]


# ============================================================
#  PHASE 3 – VIDEO PAGES
# ============================================================
async def get_gallery_video_pages(url: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            SELECT html FROM gallery_items
            WHERE gallery=? AND kind='video'
            ORDER BY idx ASC
            """,
            (url,),
        )
        rows = await cur.fetchall()

    debug_log("[get_gallery_video_pages]", url, "→", len(rows))
    return [r[0] for r in rows]
