# scraper/common/bundle_helpers.py

import os
from pathlib import Path
from typing import Optional

from .bundle_cache import (
    GalleryBundle,
    VIDEO_EXTS,
    IMAGE_EXTS,
)


# ------------------------------------------------------------
#  A single shared bundle instance for entire scraper runtime
# ------------------------------------------------------------
BUNDLE = GalleryBundle()


# ------------------------------------------------------------
#  Query bundle for a file based on prefix (e.g. "gallery-12")
# ------------------------------------------------------------
def bundle_has_file(gallery: str, prefix: str) -> Optional[str]:
    """
    Returns the bundle filename (e.g. 'images/gallery-12.jpg')
    if the gallery contains a file whose name starts with <prefix>.
    Otherwise returns None.
    """
    try:
        g = BUNDLE.index["galleries"].get(gallery, {})
        files = g.get("files", {})
        for fname in files:
            if fname.startswith(prefix):
                return fname
        return None
    except Exception:
        return None


# ------------------------------------------------------------
#  Commit all images + videos from disk into bundle
# ------------------------------------------------------------
def commit_gallery_from_disk(
    gallery_name: str,
    gallery_root: Path,
    bundle: Optional[GalleryBundle] = None,
    save_after: bool = True,
) -> GalleryBundle:
    """
    Scan a gallery folder on disk and insert all valid assets
    (images + videos) into the bundle.

    Expected layout:
        downloads/<tag>/<gallery_name>/
            images/
            videos/
    """

    gallery_root = Path(gallery_root)

    # Use global bundle if no custom bundle passed
    if bundle is None:
        bundle = BUNDLE

    if not gallery_root.exists():
        return bundle

    for root, _, files in os.walk(gallery_root):
        root_path = Path(root)

        for fname in files:
            full_path = root_path / fname
            rel_path = full_path.relative_to(gallery_root).as_posix()

            ext = full_path.suffix.lower()
            if ext not in IMAGE_EXTS and ext not in VIDEO_EXTS:
                continue  # skip non-media

            # Only commit if not already in bundle
            if not bundle_has_file(gallery_name, Path(rel_path).stem):
                with full_path.open("rb") as f:
                    data = f.read()
                bundle.add_file(gallery_name, rel_path, data)

    if save_after:
        bundle.save_index()

    return bundle
