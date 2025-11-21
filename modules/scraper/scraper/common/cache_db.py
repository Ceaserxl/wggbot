# ============================================================
#  cache_db.py — Async SQLite Cache Layer
#  Location: scraper/common/cache_db.py
# ============================================================

import os
import time
import aiosqlite
from pathlib import Path

# ------------------------------------------------------------
#  Resolve DB path relative to this file (not CWD)
# ------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / "cache"
DB_PATH = CACHE_DIR / "cache.db"

# ------------------------------------------------------------
#  Table definitions
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
    gallery    TEXT PRIMARY KEY,
    box_count  INTEGER,
    img_count  INTEGER,
    vid_count  INTEGER,
    scanned_at INTEGER
);

-- All gallery items (image/video)
CREATE TABLE IF NOT EXISTS gallery_items (
    gallery TEXT,
    idx     INTEGER,
    kind    TEXT,
    html    TEXT,
    PRIMARY KEY (gallery, idx)
);

CREATE INDEX IF NOT EXISTS idx_gallery_items_gallery_kind
    ON gallery_items(gallery, kind);

-- Tag history for --last usage
CREATE TABLE IF NOT EXISTS history_tags (
    tag      TEXT PRIMARY KEY,
    added_at INTEGER
);
"""


# ============================================================
#  INIT
# ============================================================
async def init_db():
    """Create DB + tables if missing."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(CREATE_TABLES)
        await db.commit()


# ============================================================
#  TAG CACHE
# ============================================================
async def load_tag(tag: str, ttl_days: int | None = None):
    """
    Lookup galleries for a tag.
    ttl_days is accepted for compatibility but currently ignored.
    """
    tag = tag.lower()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT gallery FROM tag_gallery WHERE tag=?",
            (tag,),
        )
        rows = await cur.fetchall()

    return [r[0] for r in rows] if rows else None


async def save_tag(tag: str, links: list[str], ttl_days: int | None = None):
    """Replace all gallery mappings for a tag."""
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
#  TAG HISTORY (for --last)
# ============================================================
async def add_tags(tags: list[str]):
    """Record tags into history with latest timestamp."""
    now = int(time.time())

    async with aiosqlite.connect(DB_PATH) as db:
        for t in tags:
            await db.execute(
                "REPLACE INTO history_tags (tag, added_at) VALUES (?, ?)",
                (t.lower(), now),
            )
        await db.commit()


async def get_last(n: int | None = None):
    """
    Fetch tag history.
    - n=None → all tags (oldest → newest)
    - n=int → last N tags (newest → oldest)
    """
    async with aiosqlite.connect(DB_PATH) as db:
        if n is None:
            cur = await db.execute(
                "SELECT tag FROM history_tags ORDER BY added_at ASC"
            )
        else:
            cur = await db.execute(
                "SELECT tag FROM history_tags ORDER BY added_at DESC LIMIT ?",
                (n,),
            )

        rows = await cur.fetchall()

    return [r[0] for r in rows]


# ============================================================
#  GALLERY CACHE
# ============================================================
async def _is_gallery_fresh(db, gallery: str, ttl_days: int | None):
    """Return True if gallery is fresh enough (based on scanned_at)."""
    if ttl_days is None:
        return True

    cur = await db.execute(
        "SELECT scanned_at FROM galleries WHERE gallery=?",
        (gallery,),
    )
    row = await cur.fetchone()
    if not row:
        return False

    scanned_at = row[0]
    age_seconds = time.time() - scanned_at
    return age_seconds <= ttl_days * 86400


async def load_gallery(url: str, ttl_days: int | None = None):
    """
    Load cached gallery boxes (HTML snippets) if fresh.
    Returns: list[str] or None
    """
    async with aiosqlite.connect(DB_PATH) as db:

        # freshness check
        if not await _is_gallery_fresh(db, url, ttl_days):
            return None

        cur = await db.execute(
            "SELECT idx, html FROM gallery_items "
            "WHERE gallery=? ORDER BY idx ASC",
            (url,),
        )
        rows = await cur.fetchall()

    return [r[1] for r in rows] if rows else None


async def save_gallery(url: str, tag: str, snippets: list[str], ttl_days: int | None = None):
    """
    Save gallery items & metadata.
    You already store tag→URL mappings via save_tag; this only stores boxes.
    """
    now = int(time.time())

    items = []
    img_count = 0
    vid_count = 0

    # classify entries
    for idx, html in enumerate(snippets, start=1):
        h = html.lower()
        if "icon-play.svg" in h:
            kind = "video"
            vid_count += 1
        elif "<img" in h:
            kind = "image"
            img_count += 1
        else:
            continue  # ignore non-media boxes

        items.append((idx, kind, html))

    box_count = len(items)

    async with aiosqlite.connect(DB_PATH) as db:
        # wipe previous items
        await db.execute("DELETE FROM gallery_items WHERE gallery=?", (url,))

        # insert items
        for idx, kind, html in items:
            await db.execute(
                "INSERT OR REPLACE INTO gallery_items (gallery, idx, kind, html) "
                "VALUES (?, ?, ?, ?)",
                (url, idx, kind, html),
            )

        # metadata row
        await db.execute(
            "INSERT OR REPLACE INTO galleries "
            "(gallery, box_count, img_count, vid_count, scanned_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (url, box_count, img_count, vid_count, now),
        )

        await db.commit()
