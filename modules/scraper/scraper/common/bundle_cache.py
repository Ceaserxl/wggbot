# scraper/common/bundle_cache.py

import json
import struct
from pathlib import Path
from typing import Dict, Any, Optional, Iterable

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
    except Exception:
        pass


# ============================================================
#  CONSTANTS
# ============================================================
MAGIC = b"BNDLIDX"
FOOTER_SIZE = 8 + len(MAGIC)  # 8-byte size + magic

VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".avi", ".mov"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


# ============================================================
#  GALLERY BUNDLE CLASS
# ============================================================
class GalleryBundle:
    """
    Append-only media bundle file.

    Layout:
        [all file bytes][index_json][8-byte index_size][MAGIC]
    """

    def __init__(self, bundle_path: Optional[Path] = None):
        # Default: /scraper/cache/cache.bundle
        if bundle_path is None:
            bundle_path = Path(__file__).resolve().parent.parent / "cache" / "cache.bundle"

        self.path: Path = Path(bundle_path)
        self.index: Dict[str, Any] = {"galleries": {}}

        # Ensure parent dir exists
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # Ensure the bundle file exists
        if not self.path.exists():
            self.path.touch()

        # Load index
        try:
            self.index = self._load_index()
            log_bundle("[INIT] Loaded index with", len(self.index.get("galleries", {})), "galleries")
        except Exception as e:
            log_bundle("[INIT_ERROR]", e)
            self.index = {"galleries": {}}

    # --------------------------------------------------------
    #  INTERNAL: Load footer + last index
    # --------------------------------------------------------
    def _load_index(self) -> Dict[str, Any]:
        size = self.path.stat().st_size
        if size < FOOTER_SIZE:
            log_bundle("[INDEX] Empty bundle, small size")
            return {"galleries": {}}

        with self.path.open("rb") as f:
            f.seek(size - FOOTER_SIZE)
            footer = f.read(FOOTER_SIZE)

            index_size = struct.unpack(">Q", footer[:8])[0]
            magic = footer[8:]

            if magic != MAGIC:
                log_bundle("[INDEX] Invalid magic footer")
                return {"galleries": {}}

            if index_size <= 0 or index_size > (size - FOOTER_SIZE):
                log_bundle("[INDEX] Invalid index length:", index_size)
                return {"galleries": {}}

            # Seek to the JSON index start
            f.seek(size - FOOTER_SIZE - index_size)
            raw = f.read(index_size)

            try:
                return json.loads(raw.decode("utf-8"))
            except Exception as e:
                log_bundle("[ERROR_INDEX_JSON]", e)
                return {"galleries": {}}

    # --------------------------------------------------------
    #  PUBLIC API
    # --------------------------------------------------------
    def has_gallery(self, gallery: str) -> bool:
        return gallery in self.index.get("galleries", {})

    def list_galleries(self) -> Iterable[str]:
        return self.index.get("galleries", {}).keys()

    # --------------------------------------------------------
    #  Append a file to the bundle
    # --------------------------------------------------------
    def add_file(
        self,
        gallery: str,
        filename: str,
        data: bytes,
        file_type: Optional[str] = None,
    ) -> None:

        filename = filename.replace("\\", "/")  # Normalize separators

        # Detect file type
        if file_type is None:
            ext = Path(filename).suffix.lower()
            if ext in VIDEO_EXTS:
                file_type = "video"
            elif ext in IMAGE_EXTS:
                file_type = "image"
            else:
                file_type = "other"

        # Append bytes
        with self.path.open("ab") as f:
            offset = f.tell()
            f.write(data)
            size = len(data)

        # Update index
        galleries = self.index.setdefault("galleries", {})
        g_entry = galleries.setdefault(gallery, {"files": {}})

        g_entry["files"][filename] = {
            "offset": offset,
            "size": size,
            "type": file_type,
        }

        # Debug log
        log_bundle(
            "[ADD]",
            f"gallery={gallery}",
            f"file={filename}",
            f"offset={offset}",
            f"size={size}",
            f"type={file_type}",
        )

    # --------------------------------------------------------
    #  Save the index (append-only)
    # --------------------------------------------------------
    def save_index(self) -> None:
        body = json.dumps(self.index, separators=(",", ":")).encode("utf-8")
        index_size = len(body)

        with self.path.open("ab") as f:
            f.write(body)
            f.write(struct.pack(">Q", index_size))
            f.write(MAGIC)

        log_bundle("[SAVE_INDEX]", f"bytes={index_size}")

    # --------------------------------------------------------
    #  Read a single file from bundle
    # --------------------------------------------------------
    def read_file(self, gallery: str, filename: str) -> bytes:
        entry = self.index["galleries"][gallery]["files"][filename]
        offset = entry["offset"]
        size = entry["size"]

        with self.path.open("rb") as f:
            f.seek(offset)
            data = f.read(size)

        log_bundle("[READ]", f"{gallery}/{filename}", f"size={size}")
        return data

    # --------------------------------------------------------
    #  Iterate file entries for a gallery
    # --------------------------------------------------------
    def iter_gallery_files(self, gallery: str):
        g = self.index["galleries"].get(gallery)
        if not g:
            return
        for fname, info in g["files"].items():
            yield fname, info
