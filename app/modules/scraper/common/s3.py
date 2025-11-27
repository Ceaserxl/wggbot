# scraper/common/s3.py
import os
from pathlib import Path
from typing import Optional
from minio import Minio
from minio.error import S3Error

# ============================================================
#  CONFIG
# ============================================================
S3_ENABLED = True
S3_BUCKET = "thefap"

# Folder layout matches disk structure
S3_IMAGES_PREFIX = "images"   # images/<gallery>/<file>
S3_VIDEOS_PREFIX = "videos"   # videos/<gallery>/<file>

# ============================================================
#  CLIENT
# ============================================================
client = Minio(
    endpoint="192.168.0.246:9000",
    access_key="minioadmin",
    secret_key="minioadmin",
    secure=False,
)

# ============================================================
#  Ensure bucket exists
# ============================================================
def ensure_bucket():
    if not client.bucket_exists(S3_BUCKET):
        client.make_bucket(S3_BUCKET)

ensure_bucket()

# ============================================================
#  Key Builders
# ============================================================
def s3_key_image(gallery: str, filename: str) -> str:
    return f"{gallery}/{S3_IMAGES_PREFIX}/{filename}"

def s3_key_video(gallery: str, filename: str) -> str:
    return f"{gallery}/{S3_VIDEOS_PREFIX}/{filename}"

# ============================================================
#  Exists
# ============================================================
def _exists(key: str) -> bool:
    try:
        client.stat_object(S3_BUCKET, key)
        return True
    except S3Error:
        return False

def s3_has_image(gallery: str, filename: str) -> bool:
    return _exists(s3_key_image(gallery, filename))

def s3_has_video(gallery: str, filename: str) -> bool:
    return _exists(s3_key_video(gallery, filename))

# ============================================================
#  Read
# ============================================================
def _read(key: str) -> Optional[bytes]:
    try:
        obj = client.get_object(S3_BUCKET, key)
        data = obj.read()
        obj.close()     # <-- keep
        # obj.release() # <-- REMOVE THIS LINE
        return data
    except S3Error:
        return None

def s3_read_image(gallery: str, filename: str) -> Optional[bytes]:
    return _read(s3_key_image(gallery, filename))

def s3_read_video(gallery: str, filename: str) -> Optional[bytes]:
    return _read(s3_key_video(gallery, filename))

# ============================================================
#  Upload
# ============================================================
def s3_upload_image(gallery: str, filename: str, file_path: Path):
    key = s3_key_image(gallery, filename)
    try:
        client.fput_object(S3_BUCKET, key, str(file_path))
    except S3Error as e:
        print(f"⚠️ S3 upload error (image): {e}")

def s3_upload_video(gallery: str, filename: str, file_path: Path):
    key = s3_key_video(gallery, filename)
    try:
        client.fput_object(S3_BUCKET, key, str(file_path))
    except S3Error as e:
        print(f"⚠️ S3 upload error (video): {e}")

# ============================================================
#  Restore to Disk
# ============================================================
def _restore(read_func, gallery: str, filename: str, out_path: Path) -> bool:
    data = read_func(gallery, filename)
    if not data:
        return False

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)
    return True

def s3_restore_image(gallery: str, filename: str, out_path: Path) -> bool:
    return _restore(s3_read_image, gallery, filename, out_path)

def s3_restore_video(gallery: str, filename: str, out_path: Path) -> bool:
    return _restore(s3_read_video, gallery, filename, out_path)

# ============================================================
#  Sync disk → S3
# ============================================================
def sync_image_to_s3(gallery: str, file_path: Path):
    fname = file_path.name
    if not s3_has_image(gallery, fname):
        s3_upload_image(gallery, fname, file_path)

def sync_video_to_s3(gallery: str, file_path: Path):
    fname = file_path.name
    if not s3_has_video(gallery, fname):
        s3_upload_video(gallery, fname, file_path)
