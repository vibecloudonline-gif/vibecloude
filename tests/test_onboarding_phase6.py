"""Tests Fase 6 — Onboarding, embudo, estudio de mercado verificado."""
from __future__ import annotations

import json
import os
import unittest

os.environ.setdefault("SECRET_KEY", "testsecretkey123")
os.environ.setdefault("VIBECLOUD_API_KEY", "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI=")
os.environ.setdefault("BASE_DOMAIN", "vibecloud.test")
os.environ["RATE_LIMIT_PUBLIC"] = "1000/minute"

from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from database.models import (
    FUNNEL_EVENT_TYPES,
    FunnelEvent,
    Product,
    ResearchListing,
    ResearchProject,
    Settings,
    Tenant,
    User,
)
from database.session import get_session
from services.auth_service import AuthService
from services.funnel_service import get_funnel_status, track_event


def _make_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _make_tenant(session, subdomain="t1", **kw):
    defaults = dict(name=subdomain, subdomain=subdomain, has_ecommerce=True, has_landing=True, ai_tier="tienda")
    defaults.update(kw)
    tenant = Tenant(**defaults)
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    return tenant


def _make_admin(session, tenant, username="admin"):
    user = User(
        tenant_id=tenant.id,
        username=username,
        password_hash=AuthService.get_password_hash("Contrasena123!"),
        role="admin",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# FunnelEvent
# ---------------------------------------------------------------------------

class TestFunnelEvent(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()
        self.session = Session(self.engine)
        self.tenant = _make_tenant(self.session)

    def tearDown(self):
        self.session.close()

    def test_track_event_creates(self):
        evt = track_event(self.session, self.tenant.id, "registro")
        self.assertIsNotNone(evt)
        self.assertEqual(evt.event_type, "registro")
        self.assertEqual(evt.tenant_id, self.tenant.id)

    def test_track_event_idempotent(self):
        evt1 = track_event(self.session, self.tenant.id, "registro")
        evt2 = track_event(self.session, self.tenant.id, "registro")
        self.assertEqual(evt1.id, evt2.id)
        count = self.session.exec(
            select(FunnelEvent).where(
                FunnelEvent.tenant_id == self.tenant.id,
                FunnelEvent.event_type == "registro",
            )
        ).all()
        self.assertEqual(len(count), 1)

    def test_track_event_unknown_type_returns_none(self):
        result = track_event(self.session, self.tenant.id, "unknown_event")
        self.assertIsNone(result)

    def test_track_event_with_metadata(self):
        meta = {"source": "signup_form", "ip": "127.0.0.1"}
        evt = track_event(self.session, self.tenant.id, "registro", metadata=meta)
        self.assertIsNotNone(evt.metadata_json)
        parsed = json.loads(evt.metadata_json)
        self.assertEqual(parsed["source"], "signup_form")

    def test_track_event_with_user_id(self):
        user = _make_admin(self.session, self.tenant)
        evt = track_event(self.session, self.tenant.id, "registro", user_id=user.id)
        self.assertEqual(evt.user_id, user.id)

    def test_get_funnel_status_empty(self):
        status = get_funnel_status(self.session, self.tenant.id)
        self.assertEqual(len(status), len(FUNNEL_EVENT_TYPES))
        for evt_type in FUNNEL_EVENT_TYPES:
            self.assertFalse(status[evt_type]["completed"])
            self.assertIsNone(status[evt_type]["date"])

    def test_get_funnel_status_with_events(self):
        track_event(self.session, self.tenant.id, "registro")
        track_event(self.session, self.tenant.id, "sitio_generado")
        status = get_funnel_status(self.session, self.tenant.id)
        self.assertTrue(status["registro"]["completed"])
        self.assertTrue(status["sitio_generado"]["completed"])
        self.assertFalse(status["primer_producto"]["completed"])

    def test_funnel_events_isolated_per_tenant(self):
        tenant2 = _make_tenant(self.session, subdomain="t2")
        track_event(self.session, self.tenant.id, "registro")
        status2 = get_funnel_status(self.session, tenant2.id)
        self.assertFalse(status2["registro"]["completed"])


# ---------------------------------------------------------------------------
# Onboarding — Productos
# ---------------------------------------------------------------------------

class TestOnboardingProductos(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()
        self.session = Session(self.engine)
        self.tenant = _make_tenant(self.session)
        self.admin = _make_admin(self.session, self.tenant)
        self.settings = Settings(tenant_id=self.tenant.id, company_name="Test")
        self.session.add(self.settings)
        self.session.commit()

        from main import app
        _session = self.session

        def _override():
            yield _session

        app.dependency_overrides[get_session] = _override

        from core.limiter import limiter
        limiter._storage.reset()

        self.client = TestClient(app)
        self.client.post(
            "/login",
            data={"username": "admin", "password": "Contrasena123!"},
            follow_redirects=False,
        )

    def tearDown(self):
        from main import app
        app.dependency_overrides.clear()
        self.session.close()

    def test_create_products_via_onboarding(self):
        resp = self.client.post(
            "/panel/onboarding/productos",
            json={
                "products": [
                    {"name": "Remera", "price": 2500, "description": "Algodón", "category": "Ropa"},
                    {"name": "Pantalón", "price": 4500},
                ]
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["products_created"], 2)
        products = self.session.exec(
            select(Product).where(Product.tenant_id == self.tenant.id)
        ).all()
        self.assertEqual(len(products), 2)

    def test_max_5_products_in_onboarding(self):
        products = [{"name": f"P{i}", "price": 100} for i in range(7)]
        resp = self.client.post(
            "/panel/onboarding/productos",
            json={"products": products},
        )
        self.assertEqual(resp.status_code, 400)

    def test_empty_products_rejected(self):
        resp = self.client.post(
            "/panel/onboarding/productos",
            json={"products": []},
        )
        self.assertEqual(resp.status_code, 400)

    def test_primer_producto_event_emitted(self):
        self.client.post(
            "/panel/onboarding/productos",
            json={"products": [{"name": "Remera", "price": 2500}]},
        )
        evt = self.session.exec(
            select(FunnelEvent).where(
                FunnelEvent.tenant_id == self.tenant.id,
                FunnelEvent.event_type == "primer_producto",
            )
        ).first()
        self.assertIsNotNone(evt)

    def test_product_limit_respected(self):
        self.tenant.ai_tier = "inicial"
        self.session.add(self.tenant)
        self.session.commit()
        for i in range(30):
            self.session.add(Product(
                tenant_id=self.tenant.id, name=f"P{i}", price=10.0, barcode=f"OB{i:04d}",
            ))
        self.session.commit()
        resp = self.client.post(
            "/panel/onboarding/productos",
            json={"products": [{"name": "Extra", "price": 100}]},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["products_created"], 0)


# ---------------------------------------------------------------------------
# Signup emite evento de registro
# ---------------------------------------------------------------------------

class TestSignupFunnelEvent(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()

        from main import app

        def override():
            with Session(self.engine) as s:
                yield s

        app.dependency_overrides[get_session] = override
        self.client = TestClient(app)

    def tearDown(self):
        from main import app
        app.dependency_overrides.clear()

    def test_signup_creates_registro_event(self):
        resp = self.client.post(
            "/registro",
            data={
                "empresa": "FunnelCo",
                "subdominio": "funnelco",
                "admin_username": "funneluser",
                "admin_password": "Contrasena123!",
                "admin_email": "funnel@example.com",
                "has_ecommerce": "true",
            },
            follow_redirects=False,
        )
        self.assertIn(resp.status_code, [302, 303])

        with Session(self.engine) as s:
            tenant = s.exec(select(Tenant).where(Tenant.subdomain == "funnelco")).first()
            self.assertIsNotNone(tenant)
            evt = s.exec(
                select(FunnelEvent).where(
                    FunnelEvent.tenant_id == tenant.id,
                    FunnelEvent.event_type == "registro",
                )
            ).first()
            self.assertIsNotNone(evt)


# ---------------------------------------------------------------------------
# Research — campos verificados
# ---------------------------------------------------------------------------

class TestResearchVerification(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()
        self.session = Session(self.engine)
        self.tenant = _make_tenant(self.session)

    def tearDown(self):
        self.session.close()

    def test_listing_has_verification_fields(self):
        project = ResearchProject(
            tenant_id=self.tenant.id, user_id=1,
            project_type="physical_product",
            query_description="test", status="completed",
        )
        self.session.add(project)
        self.session.commit()
        self.session.refresh(project)

        listing = ResearchListing(
            project_id=project.id,
            source="Amazon", title="Test Product",
            price=29.99, currency="USD",
            url="https://amazon.com/dp/123",
            verified=True,
            verification_details='{"gemini": {"confirmed": true}, "qwen": {"confirmed": true}}',
        )
        self.session.add(listing)
        self.session.commit()
        self.session.refresh(listing)

        self.assertTrue(listing.verified)
        self.assertIsNotNone(listing.verification_details)
        details = json.loads(listing.verification_details)
        self.assertTrue(details["gemini"]["confirmed"])

    def test_unverified_listing_default(self):
        project = ResearchProject(
            tenant_id=self.tenant.id, user_id=1,
            project_type="physical_product",
            query_description="test", status="completed",
        )
        self.session.add(project)
        self.session.commit()

        listing = ResearchListing(
            project_id=project.id,
            source="Test", title="Unverified",
        )
        self.session.add(listing)
        self.session.commit()
        self.session.refresh(listing)

        self.assertFalse(listing.verified)
        self.assertIsNone(listing.verification_details)

    def test_source_date_populated(self):
        from datetime import datetime, timezone
        project = ResearchProject(
            tenant_id=self.tenant.id, user_id=1,
            project_type="physical_product",
            query_description="test", status="completed",
        )
        self.session.add(project)
        self.session.commit()
        self.session.refresh(project)

        now = datetime.now(timezone.utc)
        listing = ResearchListing(
            project_id=project.id,
            source="Amazon", title="Product",
            source_date=now,
        )
        self.session.add(listing)
        self.session.commit()
        self.session.refresh(listing)

        self.assertIsNotNone(listing.source_date)


# ---------------------------------------------------------------------------
# Onboarding stepper tiene paso Productos
# ---------------------------------------------------------------------------

class TestOnboardingTemplate(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()
        self.session = Session(self.engine)
        self.tenant = _make_tenant(self.session, has_ecommerce=True, has_landing=True)
        self.admin = _make_admin(self.session, self.tenant)
        self.settings = Settings(tenant_id=self.tenant.id, company_name="Test")
        self.session.add(self.settings)
        self.session.commit()

        from main import app
        _session = self.session

        def _override():
            yield _session

        app.dependency_overrides[get_session] = _override

        from core.limiter import limiter
        limiter._storage.reset()

        self.client = TestClient(app)
        self.client.post(
            "/login",
            data={"username": "admin", "password": "Contrasena123!"},
            follow_redirects=False,
        )

    def tearDown(self):
        from main import app
        app.dependency_overrides.clear()
        self.session.close()

    def test_onboarding_page_has_productos_step(self):
        resp = self.client.get("/panel/onboarding")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Productos", resp.text)
        self.assertIn("section-productos", resp.text)
        self.assertIn("submitProductos", resp.text)

    def test_onboarding_page_has_skip_button(self):
        resp = self.client.get("/panel/onboarding")
        self.assertIn("Saltar", resp.text)

    def test_onboarding_page_has_excel_import_link(self):
        resp = self.client.get("/panel/onboarding")
        self.assertIn("catalog-import", resp.text)


# ---------------------------------------------------------------------------
# FunnelEvent model
# ---------------------------------------------------------------------------

class TestFunnelEventModel(unittest.TestCase):
    def test_all_event_types_defined(self):
        expected = {
            "registro", "sitio_generado", "primer_producto",
            "tienda_publicada", "checkout_conectado",
            "primer_pago", "activo_dia_30",
        }
        self.assertEqual(set(FUNNEL_EVENT_TYPES), expected)

    def test_unique_constraint_tenant_event(self):
        engine = _make_engine()
        with Session(engine) as session:
            tenant = _make_tenant(session, subdomain="uc-test")
            session.add(FunnelEvent(tenant_id=tenant.id, event_type="registro"))
            session.commit()

            from sqlalchemy.exc import IntegrityError
            session.add(FunnelEvent(tenant_id=tenant.id, event_type="registro"))
            with self.assertRaises(IntegrityError):
                session.commit()


# ---------------------------------------------------------------------------
# Research verification endpoint exists
# ---------------------------------------------------------------------------

class TestResearchVerificationEndpoint(unittest.TestCase):
    def test_verify_endpoint_registered(self):
        from main import app
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        self.assertIn("/panel/research/{project_id}/verificar", routes)


if __name__ == "__main__":
    unittest.main()
