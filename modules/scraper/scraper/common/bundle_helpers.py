# scraper/common/bundle_helpers.py

import os
from pathlib import Path
from typing import Optional

from .bundle_cache import (
    GalleryBundle,
    VIDEO_EXTS,
    IMAGE_EXTS,
)

# ============================================================
#  DEBUG
# ============================================================
debug = True  # toggle bundle debug logging

# Paths
CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DEBUG = CACHE_DIR / "cache_debug.txt"


def log_bundle(*msg):
    """Write a debug line into cache/cache_debug.txt if debug=True."""
    if not debug:
        return
    try:
        with CACHE_DEBUG.open("a", encoding="utf-8") as f:
            f.write(" ".join(str(m) for m in msg) + "\n")
    except Exception as e:
        print("Bundle debug log error:", e)


# ============================================================
#  GLOBAL BUNDLE
# ============================================================
BUNDLE = GalleryBundle()


# ============================================================
#  Query bundle for a file based on prefix
# ============================================================
def bundle_has_file(gallery: str, prefix: str, kind: str) -> Optional[str]:
    """
    kind = "image" or "video"
    Ensures we only match files inside the correct folder.
    """
    try:
        g = BUNDLE.index["galleries"].get(gallery, {})
        files = g.get("files", {})

        # folder filter
        folder = "images/" if kind == "image" else "videos/"

        for fname in files:
            if not fname.startswith(folder):
                continue

            # Compare filename portion
            if Path(fname).stem.startswith(prefix):
                return fname

        return None
    except Exception:
        return None

# ============================================================
#  Commit all images + videos from disk into bundle
# ============================================================
def commit_gallery_from_disk(
    gallery_name: str,
    gallery_root: Path,
    bundle: Optional[GalleryBundle] = None,
    save_after: bool = True,
) -> GalleryBundle:
    """
    Scan a gallery folder on disk and insert all valid assets
    (images + videos) into the bundle.
    """

    gallery_root = Path(gallery_root)

    # Use global shared bundle if none provided
    if bundle is None:
        bundle = BUNDLE

    if not gallery_root.exists():
        log_bundle(f"[SKIP] Gallery root missing: {gallery_root}")
        return bundle

    log_bundle(f"[SCAN] {gallery_name} -> {gallery_root}")

    for root, _, files in os.walk(gallery_root):
        root_path = Path(root)

        for fname in files:
            full_path = root_path / fname
            rel_path = full_path.relative_to(gallery_root).as_posix()

            ext = full_path.suffix.lower()
            if ext not in IMAGE_EXTS and ext not in VIDEO_EXTS:
                continue  # Skip non-media

            prefix = Path(rel_path).stem  # gallery-12 or similar

            # Already inside bundle?
            if bundle_has_file(gallery_name, prefix):
                log_bundle(f"[SKIP] Exists in bundle: {gallery_name}/{rel_path}")
                continue

            try:
                data = full_path.read_bytes()
                bundle.add_file(gallery_name, rel_path, data)
                log_bundle(f"[ADD] {gallery_name}/{rel_path} ({len(data)} bytes)")
            except Exception as e:
                log_bundle(f"[ERROR] Failed reading {full_path}: {e}")

    if save_after:
        bundle.save_index()
        log_bundle(f"[SAVE] Index updated for {gallery_name}")

    return bundle
