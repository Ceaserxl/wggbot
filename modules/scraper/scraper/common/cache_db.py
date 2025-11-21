import os
import time
import aiosqlite

DB_PATH = "cache/cache.db"

CREATE_TABLES = """
-- 1) Tag → gallery mapping (many rows per tag)
CREATE TABLE IF NOT EXISTS tag_gallery (
    tag     TEXT,
    gallery TEXT
);

CREATE INDEX IF NOT EXISTS idx_tag_gallery_tag
    ON tag_gallery(tag);
CREATE INDEX IF NOT EXISTS idx_tag_gallery_gallery
    ON tag_gallery(gallery);

-- 2) Gallery metadata
CREATE TABLE IF NOT EXISTS galleries (
    gallery    TEXT PRIMARY KEY,   -- the URL (or slug) used as key
    box_count  INTEGER,            -- total boxes we kept
    img_count  INTEGER,            -- image boxes
    vid_count  INTEGER,            -- video boxes
    scanned_at INTEGER             -- unix timestamp
);

-- 3) All boxes (images + videos) in one table
CREATE TABLE IF NOT EXISTS gallery_items (
    gallery   TEXT,
    idx       INTEGER,            -- 1..N stable index per scan
    kind      TEXT,               -- 'image' or 'video'
    html      TEXT,               -- box.outerHTML

    PRIMARY KEY (gallery, idx)
);

CREATE INDEX IF NOT EXISTS idx_gallery_items_gallery_kind
    ON gallery_items(gallery, kind);

-- 4) Tag history for --last
CREATE TABLE IF NOT EXISTS history_tags (
    tag      TEXT PRIMARY KEY,
    added_at INTEGER
);
"""


async def init_db():
    """Ensure DB file and all tables exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(CREATE_TABLES)
        await db.commit()


# ============================================================
#  TAG CACHE  (tag ↔ galleries)
# ============================================================
async def load_tag(tag: str, ttl_days: int | None = None):
    """
    Return list of gallery URLs for this tag, or None if we have nothing.
    ttl_days is accepted for compatibility but currently ignored.
    """
    tag = tag.lower()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT gallery FROM tag_gallery WHERE tag=?",
            (tag,),
        )
        rows = await cur.fetchall()

    if not rows:
        return None

    return [r[0] for r in rows]


async def save_tag(tag: str, links: list[str], ttl_days: int | None = None):
    """
    Replace all known galleries for this tag with the provided list.
    ttl_days is accepted for compatibility but currently ignored.
    """
    tag = tag.lower()
    async with aiosqlite.connect(DB_PATH) as db:
        # clear existing rows for this tag
        await db.execute("DELETE FROM tag_gallery WHERE tag=?", (tag,))
        # insert fresh mappings
        for g in links:
            await db.execute(
                "INSERT INTO tag_gallery (tag, gallery) VALUES (?, ?)",
                (tag, g),
            )
        await db.commit()


# ============================================================
#  TAG HISTORY  (--last support)
# ============================================================
async def add_tags(tags: list[str]):
    """
    Record tags into history_tags for later --last lookups.
    New inserts overwrite the timestamp so the most recent use wins.
    """
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
    Return tags from history.
    - n is None  → all tags in ascending (oldest→newest) order
    - n is int   → last n tags in descending (newest→oldest) order
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
#  GALLERY CACHE  (metadata + per-box HTML)
# ============================================================
async def _is_gallery_fresh(db, gallery: str, ttl_days: int | None):
    """
    Helper: check galleries.scanned_at against ttl_days.
    Returns True if we consider the gallery fresh.
    """
    if ttl_days is None:
        return True

    cur = await db.execute(
        "SELECT scanned_at FROM galleries WHERE gallery=?",
        (gallery,),
    )
    row = await cur.fetchone()
    if not row or row[0] is None:
        return False

    scanned_at = row[0]
    age = time.time() - scanned_at
    return age <= ttl_days * 86400


async def load_gallery(url: str, ttl_days: int | None = None):
    """
    Return list of box HTML snippets for this gallery, or None if missing/stale.
    This replaces the old JSON-based cache and is backed by gallery_items now.
    """
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

    return [r[1] for r in rows]


async def save_gallery(url: str, tag: str, snippets: list[str], ttl_days: int | None = None):
    """
    Persist a full gallery scan.

    - url: gallery URL (used as key)
    - tag: current tag (tag→gallery mapping is managed by save_tag, not here)
    - snippets: list of box.outerHTML strings as produced by the live scan

    ttl_days is accepted for compatibility but not used directly (we store scanned_at).
    """
    now = int(time.time())

    # Classify each snippet into image/video based on its HTML content.
    items: list[tuple[int, str, str]] = []
    img_count = 0
    vid_count = 0

    for idx, html in enumerate(snippets, start=1):
        lower = html.lower()
        if "icon-play.svg" in lower:
            kind = "video"
            vid_count += 1
        elif "<img" in lower:
            kind = "image"
            img_count += 1
        else:
            # ignore boxes that are neither clear images nor videos
            continue
        items.append((idx, kind, html))

    box_count = len(items)

    async with aiosqlite.connect(DB_PATH) as db:
        # wipe old items for this gallery
        await db.execute("DELETE FROM gallery_items WHERE gallery=?", (url,))

        # insert new items
        for idx, kind, html in items:
            await db.execute(
                "INSERT OR REPLACE INTO gallery_items (gallery, idx, kind, html) "
                "VALUES (?, ?, ?, ?)",
                (url, idx, kind, html),
            )

        # update metadata
        await db.execute(
            "INSERT OR REPLACE INTO galleries "
            "(gallery, box_count, img_count, vid_count, scanned_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (url, box_count, img_count, vid_count, now),
        )

        await db.commit()
