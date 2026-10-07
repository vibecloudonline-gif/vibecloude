"""Tests Fase 5 — Planes y límites."""
from __future__ import annotations

import os
import unittest
from decimal import Decimal

os.environ.setdefault("SECRET_KEY", "testsecretkey123")
os.environ.setdefault("VIBECLOUD_API_KEY", "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI=")

from sqlmodel import Session, create_engine, SQLModel, select
from sqlalchemy import text

from database.models import Product, Tenant, User
from services.plan_service import (
    PLAN_DEFINITIONS,
    check_product_limit,
    check_user_limit,
    deduct_credits_atomic,
    get_credits_per_month,
    get_max_products,
    get_max_users,
    get_plan,
    get_plan_label,
    get_plan_usage,
    get_regen_limit,
    get_storage_limit,
    resolve_tier,
)


def _make_engine():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return engine


class TestPlanDefinitions(unittest.TestCase):
    def test_three_plans_exist(self):
        self.assertIn("inicial", PLAN_DEFINITIONS)
        self.assertIn("tienda", PLAN_DEFINITIONS)
        self.assertIn("comercio", PLAN_DEFINITIONS)

    def test_prices_match_claude_md(self):
        self.assertEqual(PLAN_DEFINITIONS["inicial"]["price"], Decimal("3.97"))
        self.assertEqual(PLAN_DEFINITIONS["tienda"]["price"], Decimal("19.00"))
        self.assertEqual(PLAN_DEFINITIONS["comercio"]["price"], Decimal("49.00"))

    def test_credits_per_month(self):
        self.assertEqual(get_credits_per_month("inicial"), 30)
        self.assertEqual(get_credits_per_month("tienda"), 500)
        self.assertEqual(get_credits_per_month("comercio"), 2000)

    def test_regen_limits(self):
        self.assertEqual(get_regen_limit("inicial"), 5)
        self.assertEqual(get_regen_limit("tienda"), 40)
        self.assertEqual(get_regen_limit("comercio"), 200)

    def test_max_products(self):
        self.assertEqual(get_max_products("inicial"), 30)
        self.assertIsNone(get_max_products("tienda"))
        self.assertIsNone(get_max_products("comercio"))

    def test_storage_limits(self):
        self.assertEqual(get_storage_limit("inicial"), 250 * 1024 * 1024)
        self.assertEqual(get_storage_limit("tienda"), 2 * 1024 * 1024 * 1024)
        self.assertEqual(get_storage_limit("comercio"), 10 * 1024 * 1024 * 1024)

    def test_max_users(self):
        self.assertEqual(get_max_users("inicial"), 1)
        self.assertEqual(get_max_users("tienda"), 1)
        self.assertEqual(get_max_users("comercio"), 5)

    def test_labels(self):
        self.assertEqual(get_plan_label("inicial"), "Inicial")
        self.assertEqual(get_plan_label("tienda"), "Tienda")
        self.assertEqual(get_plan_label("comercio"), "Comercio")


class TestTierAliases(unittest.TestCase):
    def test_old_names_resolve(self):
        self.assertEqual(resolve_tier("free"), "inicial")
        self.assertEqual(resolve_tier("starter"), "tienda")
        self.assertEqual(resolve_tier("growth"), "comercio")

    def test_new_names_passthrough(self):
        self.assertEqual(resolve_tier("inicial"), "inicial")
        self.assertEqual(resolve_tier("tienda"), "tienda")
        self.assertEqual(resolve_tier("comercio"), "comercio")

    def test_unknown_passthrough(self):
        self.assertEqual(resolve_tier("unknown"), "unknown")

    def test_get_plan_with_alias(self):
        plan_free = get_plan("free")
        plan_inicial = get_plan("inicial")
        self.assertEqual(plan_free["price"], plan_inicial["price"])


class TestProductLimit(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()
        self.session = Session(self.engine)
        self.tenant = Tenant(name="T1", subdomain="t1", nivel=1, ai_tier="inicial")
        self.session.add(self.tenant)
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def test_under_limit_allows(self):
        self.assertTrue(check_product_limit(self.session, self.tenant.id, "inicial"))

    def test_at_limit_denies(self):
        for i in range(30):
            self.session.add(Product(
                tenant_id=self.tenant.id, name=f"P{i}", price=10.0,
                barcode=f"BC{i:04d}",
            ))
        self.session.commit()
        self.assertFalse(check_product_limit(self.session, self.tenant.id, "inicial"))

    def test_tienda_no_limit(self):
        for i in range(50):
            self.session.add(Product(
                tenant_id=self.tenant.id, name=f"P{i}", price=10.0,
                barcode=f"BC{i:04d}",
            ))
        self.session.commit()
        self.assertTrue(check_product_limit(self.session, self.tenant.id, "tienda"))

    def test_deleted_not_counted(self):
        for i in range(30):
            self.session.add(Product(
                tenant_id=self.tenant.id, name=f"P{i}", price=10.0,
                barcode=f"BC{i:04d}", is_deleted=True,
            ))
        self.session.commit()
        self.assertTrue(check_product_limit(self.session, self.tenant.id, "inicial"))


class TestUserLimit(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()
        self.session = Session(self.engine)
        self.tenant = Tenant(name="T1", subdomain="t1", nivel=1, ai_tier="inicial")
        self.session.add(self.tenant)
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def test_one_user_blocks_segunda(self):
        self.session.add(User(
            tenant_id=self.tenant.id, username="admin",
            password_hash="x", role="admin",
        ))
        self.session.commit()
        self.assertFalse(check_user_limit(self.session, self.tenant.id, "inicial"))

    def test_comercio_allows_five(self):
        for i in range(4):
            self.session.add(User(
                tenant_id=self.tenant.id, username=f"user{i}",
                password_hash="x", role="seller",
            ))
        self.session.commit()
        self.assertTrue(check_user_limit(self.session, self.tenant.id, "comercio"))

    def test_comercio_blocks_sixth(self):
        for i in range(5):
            self.session.add(User(
                tenant_id=self.tenant.id, username=f"user{i}",
                password_hash="x", role="seller",
            ))
        self.session.commit()
        self.assertFalse(check_user_limit(self.session, self.tenant.id, "comercio"))


class TestAtomicCredits(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()
        self.session = Session(self.engine)
        self.tenant = Tenant(
            name="T1", subdomain="t1", nivel=1,
            ai_tier="inicial", ai_credits=10,
        )
        self.session.add(self.tenant)
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def test_deduct_success(self):
        ok = deduct_credits_atomic(self.session, self.tenant.id, 5)
        self.assertTrue(ok)
        self.session.refresh(self.tenant)
        self.assertEqual(self.tenant.ai_credits, 5)

    def test_deduct_exact(self):
        ok = deduct_credits_atomic(self.session, self.tenant.id, 10)
        self.assertTrue(ok)
        self.session.refresh(self.tenant)
        self.assertEqual(self.tenant.ai_credits, 0)

    def test_deduct_insufficient(self):
        ok = deduct_credits_atomic(self.session, self.tenant.id, 11)
        self.assertFalse(ok)
        self.session.refresh(self.tenant)
        self.assertEqual(self.tenant.ai_credits, 10)

    def test_multiple_deductions(self):
        deduct_credits_atomic(self.session, self.tenant.id, 3)
        deduct_credits_atomic(self.session, self.tenant.id, 3)
        deduct_credits_atomic(self.session, self.tenant.id, 3)
        self.session.refresh(self.tenant)
        self.assertEqual(self.tenant.ai_credits, 1)
        ok = deduct_credits_atomic(self.session, self.tenant.id, 3)
        self.assertFalse(ok)
        self.session.refresh(self.tenant)
        self.assertEqual(self.tenant.ai_credits, 1)


class TestPlanUsage(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()
        self.session = Session(self.engine)
        self.tenant = Tenant(
            name="T1", subdomain="t1", nivel=1,
            ai_tier="tienda", ai_credits=200,
            landing_regen_count=5,
        )
        self.session.add(self.tenant)
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def test_usage_returns_correct_data(self):
        usage = get_plan_usage(self.session, self.tenant.id, "tienda")
        self.assertEqual(usage["plan_slug"], "tienda")
        self.assertEqual(usage["plan_label"], "Tienda")
        self.assertEqual(usage["plan_price"], Decimal("19.00"))
        self.assertEqual(usage["credits_per_month"], 500)
        self.assertEqual(usage["credits_remaining"], 200)
        self.assertEqual(usage["regen_limit"], 40)
        self.assertEqual(usage["regen_used"], 5)
        self.assertIsNone(usage["max_products"])
        self.assertEqual(usage["max_users"], 1)


class TestPlanPageEndpoint(unittest.TestCase):
    def test_panel_plan_route_exists(self):
        from fastapi.testclient import TestClient
        from sqlalchemy.pool import StaticPool
        from sqlmodel import create_engine as ce

        engine = ce("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(engine)

        with Session(engine) as s:
            tenant = Tenant(name="T1", subdomain="t1", nivel=1, ai_tier="inicial", ai_credits=30)
            s.add(tenant)
            s.commit()
            s.refresh(tenant)
            from database.models import Settings as SettingsModel
            s.add(SettingsModel(tenant_id=tenant.id, business_name="Test"))
            admin = User(
                tenant_id=tenant.id, username="admin",
                password_hash="$argon2id$v=19$m=65536,t=3,p=4$dGVzdHNhbHQ$hash",
                role="admin",
            )
            s.add(admin)
            s.commit()

        from database.session import get_session
        from main import app

        def override():
            with Session(engine) as s:
                yield s

        app.dependency_overrides[get_session] = override
        client = TestClient(app)
        resp = client.get("/panel/plan")
        self.assertIn(resp.status_code, [200, 302, 303, 307])
        app.dependency_overrides.clear()


class TestLandingCascadeOrder(unittest.TestCase):
    def test_gemini_is_primary(self):
        import inspect
        from services.ai_gateway_service import AIGatewayService
        source = inspect.getsource(AIGatewayService.generate_landing_content_cascade)
        gemini_pos = source.find("Gemini (primary")
        claude_pos = source.find("Claude (fallback")
        self.assertGreater(gemini_pos, -1, "Gemini should be labeled as primary")
        self.assertGreater(claude_pos, -1, "Claude should be labeled as fallback")
        self.assertLess(gemini_pos, claude_pos, "Gemini should come before Claude")


class TestPaymentsPlansConsistency(unittest.TestCase):
    def test_payments_plans_match_plan_definitions(self):
        from routers.payments import PLANS
        for slug, plan_def in PLAN_DEFINITIONS.items():
            self.assertIn(slug, PLANS)
            self.assertEqual(PLANS[slug]["price"], plan_def["price"])
            self.assertEqual(PLANS[slug]["credits"], plan_def["credits_per_month"])


class TestStorageLimitsConsistency(unittest.TestCase):
    def test_storage_limits_match_plan_definitions(self):
        from services.storage_service import PLAN_STORAGE_LIMITS
        for slug, plan_def in PLAN_DEFINITIONS.items():
            self.assertIn(slug, PLAN_STORAGE_LIMITS)
            self.assertEqual(PLAN_STORAGE_LIMITS[slug], plan_def["storage_bytes"])


class TestRegenLimitsConsistency(unittest.TestCase):
    def test_regen_limits_match_plan_definitions(self):
        from routers.landing_studio import LANDING_REGEN_LIMITS
        for slug, plan_def in PLAN_DEFINITIONS.items():
            self.assertIn(slug, LANDING_REGEN_LIMITS)
            self.assertEqual(LANDING_REGEN_LIMITS[slug], plan_def["regen_limit"])


if __name__ == "__main__":
    unittest.main()
