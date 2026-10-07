"""services/storage_service.py — Almacenamiento de archivos (local o GCS).

Interfaz única: upload / delete / get_url.
Selección por env var STORAGE_BACKEND=local|gcs.
Imágenes se re-encodean con Pillow para strip EXIF/GPS.
"""
from __future__ import annotations

import io
import logging
import os
import shutil
import uuid
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

from services.plan_service import PLAN_DEFINITIONS, get_storage_limit, resolve_tier

PLAN_STORAGE_LIMITS = {slug: p["storage_bytes"] for slug, p in PLAN_DEFINITIONS.items()}

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB por imagen

_executor = ThreadPoolExecutor(max_workers=2)


def _strip_exif_and_reencode(data: bytes, content_type: str) -> tuple[bytes, str]:
    """Re-encode imagen para strip EXIF/GPS. Devuelve (bytes, content_type)."""
    try:
        img = Image.open(io.BytesIO(data))
    except Exception:
        raise ValueError("El archivo no es una imagen válida")

    if img.mode == "RGBA" and content_type == "image/jpeg":
        img = img.convert("RGB")
    elif img.mode not in ("RGB", "RGBA", "L", "P"):
        img = img.convert("RGB")

    buf = io.BytesIO()
    fmt_map = {
        "image/jpeg": ("JPEG", ".jpg"),
        "image/png": ("PNG", ".png"),
        "image/webp": ("WEBP", ".webp"),
        "image/gif": ("GIF", ".gif"),
    }
    fmt, ext = fmt_map.get(content_type, ("JPEG", ".jpg"))

    save_kwargs: dict = {}
    if fmt == "JPEG":
        save_kwargs["quality"] = 85
        save_kwargs["optimize"] = True
    elif fmt == "PNG":
        save_kwargs["optimize"] = True
    elif fmt == "WEBP":
        save_kwargs["quality"] = 85

    img.save(buf, format=fmt, **save_kwargs)
    return buf.getvalue(), content_type


def make_storage_key(tenant_id: int, file_type: str, ext: str) -> str:
    return f"tenants/{tenant_id}/{file_type}/{uuid.uuid4().hex}{ext}"


class StorageBackend(ABC):
    @abstractmethod
    def upload(self, key: str, data: bytes, content_type: str) -> str:
        """Sube archivo. Devuelve URL pública."""
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        ...

    @abstractmethod
    def get_url(self, key: str) -> str:
        ...

    @abstractmethod
    def health_check(self) -> bool:
        ...


class LocalStorageBackend(StorageBackend):
    def __init__(self) -> None:
        self.base_dir = os.getenv("LOCAL_STORAGE_DIR", "static/uploads")

    def upload(self, key: str, data: bytes, content_type: str) -> str:
        path = os.path.join(self.base_dir, key.replace("/", os.sep))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return f"/static/uploads/{key}"

    def delete(self, key: str) -> None:
        path = os.path.join(self.base_dir, key.replace("/", os.sep))
        if os.path.exists(path):
            os.remove(path)

    def get_url(self, key: str) -> str:
        return f"/static/uploads/{key}"

    def health_check(self) -> bool:
        return os.path.isdir(self.base_dir) or self.base_dir == "static/uploads"


class GCSStorageBackend(StorageBackend):
    def __init__(self) -> None:
        self.bucket_name = os.getenv("GCS_BUCKET_NAME", "")
        self.cdn_base = os.getenv("GCS_CDN_URL", "")
        self._client = None
        self._bucket = None

    def _get_bucket(self):
        if self._bucket is None:
            from google.cloud import storage as gcs
            self._client = gcs.Client()
            self._bucket = self._client.bucket(self.bucket_name)
        return self._bucket

    def upload(self, key: str, data: bytes, content_type: str) -> str:
        bucket = self._get_bucket()
        blob = bucket.blob(key)
        blob.upload_from_string(data, content_type=content_type)
        if self.cdn_base:
            return f"{self.cdn_base.rstrip('/')}/{key}"
        return blob.public_url

    def delete(self, key: str) -> None:
        bucket = self._get_bucket()
        blob = bucket.blob(key)
        blob.delete()

    def get_url(self, key: str) -> str:
        if self.cdn_base:
            return f"{self.cdn_base.rstrip('/')}/{key}"
        bucket = self._get_bucket()
        return bucket.blob(key).public_url

    def health_check(self) -> bool:
        try:
            bucket = self._get_bucket()
            bucket.exists()
            return True
        except Exception:
            return False


def _create_backend() -> StorageBackend:
    backend = os.getenv("STORAGE_BACKEND", "local").lower()
    if backend == "gcs":
        return GCSStorageBackend()
    return LocalStorageBackend()


_backend: Optional[StorageBackend] = None


def get_storage() -> StorageBackend:
    global _backend
    if _backend is None:
        _backend = _create_backend()
    return _backend


def upload_image(
    tenant_id: int,
    file_data: bytes,
    content_type: str,
    file_type: str = "image",
    original_name: str = "",
) -> tuple[str, str, int]:
    """Valida, strip EXIF, sube. Devuelve (storage_key, public_url, size_bytes)."""
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError(f"Tipo no permitido: {content_type}")

    if len(file_data) > MAX_IMAGE_BYTES:
        raise ValueError(f"Imagen excede {MAX_IMAGE_BYTES // (1024*1024)} MB")

    clean_data, ct = _strip_exif_and_reencode(file_data, content_type)
    ext = ALLOWED_CONTENT_TYPES[ct]
    key = make_storage_key(tenant_id, file_type, ext)

    storage = get_storage()
    url = storage.upload(key, clean_data, ct)

    return key, url, len(clean_data)


def upload_image_sync(
    tenant_id: int,
    file_data: bytes,
    content_type: str,
    file_type: str = "image",
    original_name: str = "",
) -> tuple[str, str, int]:
    """Wrapper síncrono (para endpoints def)."""
    return upload_image(tenant_id, file_data, content_type, file_type, original_name)


def check_tenant_quota(current_bytes: int, new_bytes: int, plan: str) -> bool:
    limit = get_storage_limit(plan)
    return (current_bytes + new_bytes) <= limit


def get_tenant_usage(session, tenant_id: int) -> int:
    from sqlmodel import select, func
    from database.models import TenantFile
    result = session.exec(
        select(func.coalesce(func.sum(TenantFile.size_bytes), 0)).where(
            TenantFile.tenant_id == tenant_id
        )
    ).one()
    return int(result)
