# scraper/common/bundle_cache.py

import json
import struct
from pathlib import Path
from typing import Dict, Any, Optional, Iterable

MAGIC = b"BNDLIDX"
FOOTER_SIZE = 8 + len(MAGIC)  # 8-byte size + magic

VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".avi", ".mov"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


class GalleryBundle:
    """
    Append-only media bundle file.

    Layout:
        [file bytes ...][index_json][8-byte index_size][MAGIC]
    """

    def __init__(self, bundle_path: Optional[Path] = None):
        # default: cache.bundle alongside this file
        if bundle_path is None:
            bundle_path = Path(__file__).resolve().parent.parent / "cache" / "cache.bundle"


        self.path: Path = Path(bundle_path)
        self.index: Dict[str, Any] = {"galleries": {}}

        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.touch()

        try:
            self.index = self._load_index()
        except Exception:
            self.index = {"galleries": {}}

    # ---------------------------------
    # Internal: load last index footer
    # ---------------------------------
    def _load_index(self) -> Dict[str, Any]:
        size = self.path.stat().st_size
        if size < FOOTER_SIZE:
            return {"galleries": {}}

        with self.path.open("rb") as f:
            # Footer = [8-byte index_size][MAGIC]
            f.seek(size - FOOTER_SIZE)
            footer = f.read(FOOTER_SIZE)

            index_size = struct.unpack(">Q", footer[:8])[0]
            magic = footer[8:]

            if magic != MAGIC:
                return {"galleries": {}}
            if index_size <= 0 or index_size > size - FOOTER_SIZE:
                return {"galleries": {}}

            f.seek(size - FOOTER_SIZE - index_size)
            raw = f.read(index_size)
            return json.loads(raw.decode("utf-8"))

    # ---------------------------------
    # Public API
    # ---------------------------------
    def has_gallery(self, gallery: str) -> bool:
        return gallery in self.index.get("galleries", {})

    def list_galleries(self) -> Iterable[str]:
        return self.index.get("galleries", {}).keys()

    # ---------------------------------
    # Append a file to bundle
    # ---------------------------------
    def add_file(
        self,
        gallery: str,
        filename: str,
        data: bytes,
        file_type: Optional[str] = None,
    ) -> None:
        filename = filename.replace("\\", "/")

        if file_type is None:
            ext = Path(filename).suffix.lower()
            if ext in VIDEO_EXTS:
                file_type = "video"
            elif ext in IMAGE_EXTS:
                file_type = "image"
            else:
                file_type = "other"

        with self.path.open("ab") as f:
            offset = f.tell()
            f.write(data)
            size = len(data)

        galleries = self.index.setdefault("galleries", {})
        g_entry = galleries.setdefault(gallery, {"files": {}})

        g_entry["files"][filename] = {
            "offset": offset,
            "size": size,
            "type": file_type,
        }

    # ---------------------------------
    # Append index (no truncation)
    # ---------------------------------
    def save_index(self) -> None:
        body = json.dumps(self.index, separators=(",", ":")).encode("utf-8")
        index_size = len(body)

        with self.path.open("ab") as f:
            f.write(body)
            f.write(struct.pack(">Q", index_size))
            f.write(MAGIC)

    # ---------------------------------
    # Read a single file
    # ---------------------------------
    def read_file(self, gallery: str, filename: str) -> bytes:
        entry = self.index["galleries"][gallery]["files"][filename]
        offset = entry["offset"]
        size = entry["size"]

        with self.path.open("rb") as f:
            f.seek(offset)
            return f.read(size)

    # ---------------------------------
    # Iterate gallery files
    # ---------------------------------
    def iter_gallery_files(self, gallery: str):
        g = self.index["galleries"].get(gallery)
        if not g:
            return
        for fname, info in g["files"].items():
            yield fname, info
