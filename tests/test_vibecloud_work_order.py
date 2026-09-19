"""Unit tests verifying Work Order execution:
- 1.1: /reports/cash-flow imports (timezone, timedelta)
- 1.2: global_exception_handler behaves correctly in production vs development
- 1.3: inventory endpoint/router removed
- 1.4: /credits/buy security (admin check, payment reference validation, idempotency)
- 3.1 & 3.2: competitor_service functions and models
"""
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import json
import os

from sqlmodel import SQLModel, Session, create_engine
from database.models import User, Tenant, ResearchProject, CompetitorAnalysis, PlatformPayment
import services.competitor_service as comp_svc


class TestWorkOrderExecution(unittest.TestCase):

    def setUp(self):
        os.environ["SECRET_KEY"] = "test_session_secret_key_vibecloud"
        self.engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self.engine)
        self.session = Session(self.engine)

        # Base tenant
        self.tenant = Tenant(id=1, name="Tenant Test", ai_credits=100)
        self.session.add(self.tenant)

        # Users
        self.admin = User(id=1, tenant_id=1, username="admin_u", password_hash="hashed_pw", email="a@t.com", role="admin")
        self.regular_user = User(id=2, tenant_id=1, username="reg_u", password_hash="hashed_pw", email="r@t.com", role="user")
        self.session.add(self.admin)
        self.session.add(self.regular_user)

        # Project
        self.project = ResearchProject(
            id=10,
            tenant_id=1,
            user_id=1,
            project_type="physical_product",
            query_description="Auriculares bluetooth deportivos",
            status="completed",
        )
        self.session.add(self.project)
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def test_1_1_reports_imports(self):
        """Verifica que routers.reports importa timezone y timedelta sin NameError."""
        import routers.reports as rep
        self.assertTrue(hasattr(rep, "timezone"))
        self.assertTrue(hasattr(rep, "timedelta"))
        # Test the exact operation in /reports/cash-flow line 46-47
        target_day = date.today()
        start = datetime.combine(target_day, datetime.min.time()).replace(tzinfo=rep.timezone.utc)
        end = start + rep.timedelta(days=1)
        self.assertGreater(end, start)

    def test_1_2_global_exception_handler_prod_vs_dev(self):
        """Verifica que el exception handler oculta detalles en producción y loguea."""
        import main
        handler = main.global_exception_handler

        dummy_req = MagicMock()
        dummy_exc = RuntimeError("Table user_secret_data column id leak")

        import asyncio

        # Dev mode
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            resp_dev = asyncio.run(handler(dummy_req, dummy_exc))
            body_dev = json.loads(resp_dev.body.decode())
            self.assertEqual(resp_dev.status_code, 500)
            self.assertIn("Table user_secret_data", body_dev["detail"])

        # Production mode
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            resp_prod = asyncio.run(handler(dummy_req, dummy_exc))
            body_prod = json.loads(resp_prod.body.decode())
            self.assertEqual(resp_prod.status_code, 500)
            self.assertEqual(body_prod["detail"], "Error interno del servidor.")
            self.assertNotIn("Table user_secret_data", body_prod["detail"])

    def test_1_3_inventory_removed(self):
        """Verifica que routers/api/v1/inventory.py no existe y main.py no lo importa."""
        self.assertFalse(os.path.exists("routers/api/v1/inventory.py"))
        import main
        self.assertFalse(hasattr(main, "inventory_v1_router"))

    def test_1_4_credits_buy_admin_check(self):
        """Verifica que SettingsService.ensure_admin rechaza usuario no-admin."""
        from services.settings_service import SettingsService
        from fastapi import HTTPException

        # Admin pasa
        SettingsService.ensure_admin(self.admin)

        # Regular user tira 403
        with self.assertRaises(HTTPException) as ctx:
            SettingsService.ensure_admin(self.regular_user)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_1_4_credits_buy_payment_and_idempotency(self):
        """Verifica validación de PlatformPayment e idempotencia en compra de créditos."""
        from routers.ai import buy_tenant_credits, CreditPurchaseRequest
        from fastapi import HTTPException
        import asyncio

        # 1. Pago inexistente o no completado -> 402
        req = CreditPurchaseRequest(amount=50, payment_reference="pay_invalid_123")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(buy_tenant_credits(
                req=req,
                db=self.session,
                current_user=self.admin,
                tenant_id=1,
            ))
        self.assertEqual(ctx.exception.status_code, 402)

        # 2. Registrar pago completado válido
        payment = PlatformPayment(
            tenant_id=1,
            provider="stripe",
            external_id="cs_test_valid_999",
            payment_type="credit_purchase",
            amount=10.0,
            status="completed",
            metadata_json=json.dumps({"plan": "credits_50"}),
        )
        self.session.add(payment)
        self.session.commit()

        # 3. Primer intento con pago válido -> Éxito (100 + 50 = 150)
        req_valid = CreditPurchaseRequest(amount=50, payment_reference="cs_test_valid_999")
        res = asyncio.run(buy_tenant_credits(
            req=req_valid,
            db=self.session,
            current_user=self.admin,
            tenant_id=1,
        ))
        self.assertTrue(res["success"])
        self.assertEqual(res["ai_credits"], 150)

        # 4. Segundo intento con mismo pago -> 409 (Idempotencia)
        with self.assertRaises(HTTPException) as ctx2:
            asyncio.run(buy_tenant_credits(
                req=req_valid,
                db=self.session,
                current_user=self.admin,
                tenant_id=1,
            ))
        self.assertEqual(ctx2.exception.status_code, 409)

    def test_3_competitor_lifecycle(self):
        """Verifica add_competitor, list_competitors, confirm_competitor y remove_competitor."""
        # 1. Add
        comp = comp_svc.add_competitor(
            session=self.session,
            project_id=10,
            tenant_id=1,
            url="https://rivalbrand.com",
            notes="Líder con envío gratis en 24h",
        )
        self.assertIsNotNone(comp.id)
        self.assertEqual(comp.url, "https://rivalbrand.com")
        self.assertFalse(comp.user_confirmed)

        # 2. List
        comps = comp_svc.list_competitors(self.session, project_id=10, tenant_id=1)
        self.assertEqual(len(comps), 1)
        self.assertEqual(comps[0].id, comp.id)

        # 3. Confirm
        confirmed = comp_svc.confirm_competitor(self.session, competitor_id=comp.id, tenant_id=1)
        self.assertIsNotNone(confirmed)
        self.assertTrue(confirmed.user_confirmed)

        # 4. Cannot confirm from other tenant
        other_tenant_confirm = comp_svc.confirm_competitor(self.session, competitor_id=comp.id, tenant_id=999)
        self.assertIsNone(other_tenant_confirm)

        # 5. Remove
        removed = comp_svc.remove_competitor(self.session, competitor_id=comp.id, tenant_id=1)
        self.assertTrue(removed)
        comps_after = comp_svc.list_competitors(self.session, project_id=10, tenant_id=1)
        self.assertEqual(len(comps_after), 0)


if __name__ == "__main__":
    unittest.main()
