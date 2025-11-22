# scraper/common/phase3/preload.py

from pathlib import Path
from ..bundle_helpers import BUNDLE, bundle_has_file

def preload_gallery(gallery_name: str, img_dir: Path, vid_dir: Path, total_images: int, total_videos: int):
    restored_images = 0
    restored_videos = 0

    # ensure folders exist
    img_dir.mkdir(parents=True, exist_ok=True)
    vid_dir.mkdir(parents=True, exist_ok=True)

    # Restore images
    for idx in range(total_images):
        prefix = f"{gallery_name}-{idx}"

        disk_exists = any(Path(img_dir).glob(f"{prefix}.*"))
        if disk_exists:
            continue

        bundle_file = bundle_has_file(gallery_name, prefix, kind="image")
        if bundle_file:
            data = BUNDLE.read_file(gallery_name, bundle_file)
            out = img_dir / Path(bundle_file).name
            out.write_bytes(data)
            restored_images += 1

    # Restore videos
    for idx in range(total_videos):
        prefix = f"{gallery_name}-{idx}"

        disk_exists = any(Path(vid_dir).glob(f"{prefix}.*"))
        if disk_exists:
            continue

        bundle_file = bundle_has_file(gallery_name, prefix, kind="video")
        if bundle_file:
            data = BUNDLE.read_file(gallery_name, bundle_file)
            out = vid_dir / Path(bundle_file).name
            out.write_bytes(data)
            restored_videos += 1

    return restored_images, restored_videos
