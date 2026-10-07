"""Tests Fase 4 — Storage, backups, monitoreo."""
from __future__ import annotations

import io
import os
import tempfile
import unittest
from decimal import Decimal
from unittest.mock import patch, MagicMock

from PIL import Image
from sqlmodel import Session, create_engine, SQLModel, select, func

from database.models import Tenant, TenantFile


def _make_engine():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return engine


def _make_jpeg(width=100, height=100, exif=True) -> bytes:
    img = Image.new("RGB", (width, height), color="red")
    buf = io.BytesIO()
    if exif:
        exif_data = img.getexif()
        exif_data[0x010F] = "TestCamera"  # Make
        exif_data[0x0110] = "TestModel"   # Model
        exif_data[0x0132] = "2024:01:01 12:00:00"  # DateTime
        img.save(buf, format="JPEG", exif=exif_data.tobytes())
    else:
        img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_png(width=50, height=50) -> bytes:
    img = Image.new("RGBA", (width, height), color=(0, 0, 255, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestStripExif(unittest.TestCase):
    def test_jpeg_exif_stripped(self):
        from services.storage_service import _strip_exif_and_reencode
        raw = _make_jpeg(exif=True)
        clean, ct = _strip_exif_and_reencode(raw, "image/jpeg")

        img = Image.open(io.BytesIO(clean))
        exif = img.getexif()
        self.assertEqual(len(exif), 0, "EXIF data should be stripped")
        self.assertEqual(ct, "image/jpeg")

    def test_png_passthrough(self):
        from services.storage_service import _strip_exif_and_reencode
        raw = _make_png()
        clean, ct = _strip_exif_and_reencode(raw, "image/png")
        self.assertEqual(ct, "image/png")
        img = Image.open(io.BytesIO(clean))
        self.assertEqual(img.format, "PNG")

    def test_invalid_data_raises(self):
        from services.storage_service import _strip_exif_and_reencode
        with self.assertRaises(ValueError):
            _strip_exif_and_reencode(b"not an image", "image/jpeg")


class TestLocalStorageBackend(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.old_env = os.environ.get("LOCAL_STORAGE_DIR")
        os.environ["LOCAL_STORAGE_DIR"] = self.tmpdir

    def tearDown(self):
        if self.old_env:
            os.environ["LOCAL_STORAGE_DIR"] = self.old_env
        else:
            os.environ.pop("LOCAL_STORAGE_DIR", None)
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_upload_and_get_url(self):
        from services.storage_service import LocalStorageBackend
        backend = LocalStorageBackend()
        backend.base_dir = self.tmpdir

        key = "tenants/1/product/abc123.jpg"
        data = _make_jpeg(exif=False)
        url = backend.upload(key, data, "image/jpeg")

        self.assertIn(key, url)
        path = os.path.join(self.tmpdir, *key.split("/"))
        self.assertTrue(os.path.exists(path))

    def test_delete(self):
        from services.storage_service import LocalStorageBackend
        backend = LocalStorageBackend()
        backend.base_dir = self.tmpdir

        key = "tenants/1/product/del123.jpg"
        data = _make_jpeg(exif=False)
        backend.upload(key, data, "image/jpeg")
        backend.delete(key)

        path = os.path.join(self.tmpdir, *key.split("/"))
        self.assertFalse(os.path.exists(path))

    def test_health_check(self):
        from services.storage_service import LocalStorageBackend
        backend = LocalStorageBackend()
        backend.base_dir = self.tmpdir
        self.assertTrue(backend.health_check())


class TestUploadImage(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        os.environ["LOCAL_STORAGE_DIR"] = self.tmpdir
        os.environ["STORAGE_BACKEND"] = "local"
        import services.storage_service as ss
        ss._backend = None

    def tearDown(self):
        os.environ.pop("LOCAL_STORAGE_DIR", None)
        os.environ.pop("STORAGE_BACKEND", None)
        import services.storage_service as ss
        ss._backend = None
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_upload_strips_exif(self):
        from services.storage_service import upload_image
        data = _make_jpeg(exif=True)
        key, url, size = upload_image(1, data, "image/jpeg", "product")

        self.assertIn("tenants/1/product/", key)
        self.assertTrue(key.endswith(".jpg"))
        self.assertGreater(size, 0)

        path = os.path.join(self.tmpdir, *key.split("/"))
        with open(path, "rb") as f:
            img = Image.open(f)
            self.assertEqual(len(img.getexif()), 0)

    def test_rejects_invalid_content_type(self):
        from services.storage_service import upload_image
        with self.assertRaises(ValueError):
            upload_image(1, b"data", "application/pdf", "product")

    def test_rejects_oversized(self):
        from services.storage_service import upload_image
        big = _make_jpeg(3000, 3000)
        with patch("services.storage_service.MAX_IMAGE_BYTES", 100):
            with self.assertRaises(ValueError):
                upload_image(1, big, "image/jpeg", "product")

    def test_storage_key_format(self):
        from services.storage_service import make_storage_key
        key = make_storage_key(42, "product", ".png")
        self.assertTrue(key.startswith("tenants/42/product/"))
        self.assertTrue(key.endswith(".png"))
        self.assertEqual(len(key.split("/")[-1]), 36)  # uuid hex (32) + .png (4)


class TestTenantQuota(unittest.TestCase):
    def test_check_within_limit(self):
        from services.storage_service import check_tenant_quota
        self.assertTrue(check_tenant_quota(100 * 1024 * 1024, 1024, "inicial"))

    def test_check_exceeds_limit(self):
        from services.storage_service import check_tenant_quota
        self.assertFalse(check_tenant_quota(250 * 1024 * 1024, 1, "inicial"))

    def test_comercio_higher_limit(self):
        from services.storage_service import check_tenant_quota
        self.assertTrue(check_tenant_quota(5 * 1024 * 1024 * 1024, 1024, "comercio"))


class TestTenantFileModel(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()

    def test_create_and_query_usage(self):
        tenant = Tenant(name="T1", subdomain="t1", nivel=1)
        self.session.add(tenant)
        self.session.commit()

        self.session.add(TenantFile(
            tenant_id=tenant.id, storage_key="tenants/1/product/a.jpg",
            file_type="product", size_bytes=5000, public_url="/uploads/a.jpg",
        ))
        self.session.add(TenantFile(
            tenant_id=tenant.id, storage_key="tenants/1/product/b.jpg",
            file_type="product", size_bytes=3000, public_url="/uploads/b.jpg",
        ))
        self.session.commit()

        from services.storage_service import get_tenant_usage
        total = get_tenant_usage(self.session, tenant.id)
        self.assertEqual(total, 8000)

    def test_unique_storage_key(self):
        from sqlalchemy.exc import IntegrityError
        tenant = Tenant(name="T1", subdomain="t1", nivel=1)
        self.session.add(tenant)
        self.session.commit()

        self.session.add(TenantFile(
            tenant_id=tenant.id, storage_key="tenants/1/product/dup.jpg",
            size_bytes=100, public_url="/x",
        ))
        self.session.commit()

        self.session.add(TenantFile(
            tenant_id=tenant.id, storage_key="tenants/1/product/dup.jpg",
            size_bytes=200, public_url="/y",
        ))
        with self.assertRaises(IntegrityError):
            self.session.commit()
        self.session.rollback()


class TestHealthEndpoint(unittest.TestCase):
    def test_health_includes_storage(self):
        os.environ.setdefault("SECRET_KEY", "testsecretkey123")
        os.environ.setdefault("VIBECLOUD_API_KEY", "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI=")
        from fastapi.testclient import TestClient
        from sqlalchemy.pool import StaticPool
        from sqlmodel import create_engine as ce
        engine = ce("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(engine)
        from database.session import get_session
        from main import app
        def override():
            with Session(engine) as s:
                yield s
        app.dependency_overrides[get_session] = override
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "storage" in data["services"]
        assert data["services"]["storage"] == "ok"
        app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
