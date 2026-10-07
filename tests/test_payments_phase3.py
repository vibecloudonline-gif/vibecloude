"""Tests Fase 3 — Pagos: webhooks, idempotencia, comisión, stock return."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import unittest
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from sqlmodel import Session, create_engine, SQLModel, select

from database.models import (
    Bin,
    BinStock,
    Location,
    PlatformPayment,
    ProcessedWebhook,
    Product,
    Sale,
    SaleItem,
    StockMovement,
    Tenant,
    TenantPaymentConfig,
    encrypt_api_key,
)


def _make_engine():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return engine


class TestPaymentPlans(unittest.TestCase):
    def test_plans_match_claude_md(self):
        from routers.payments import PLANS
        self.assertIn("inicial", PLANS)
        self.assertIn("tienda", PLANS)
        self.assertIn("comercio", PLANS)
        self.assertEqual(PLANS["inicial"]["price"], Decimal("3.97"))
        self.assertEqual(PLANS["tienda"]["price"], Decimal("19.00"))
        self.assertEqual(PLANS["comercio"]["price"], Decimal("49.00"))
        self.assertNotIn("free", PLANS)
        self.assertNotIn("starter", PLANS)
        self.assertNotIn("growth", PLANS)


class TestWebhookIdempotency(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()
        self.session = Session(self.engine)
        self.tenant = Tenant(name="T1", subdomain="t1", nivel=1)
        self.session.add(self.tenant)
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def test_duplicate_webhook_ignored(self):
        from routers.webhooks import _already_processed, _record_processed

        event_id = "evt_123"
        source = "stripe"
        transition = "pending→paid"

        self.assertFalse(_already_processed(self.session, event_id, source, transition))
        _record_processed(self.session, event_id, source, transition)
        self.session.commit()

        self.assertTrue(_already_processed(self.session, event_id, source, transition))

    def test_different_transition_allowed(self):
        from routers.webhooks import _already_processed, _record_processed

        event_id = "evt_456"
        _record_processed(self.session, event_id, "stripe", "pending→paid")
        self.session.commit()

        self.assertFalse(_already_processed(self.session, event_id, "stripe", "paid→refunded"))


class TestPaymentStateMachine(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()
        self.session = Session(self.engine)
        self.tenant = Tenant(name="T1", subdomain="t1", nivel=1, ai_credits=100)
        self.session.add(self.tenant)
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def test_pending_to_paid_credits(self):
        from routers.webhooks import _process_payment_update

        payment = PlatformPayment(
            tenant_id=self.tenant.id,
            provider="mercadopago",
            external_id="mp_999",
            external_ref=uuid.uuid4().hex,
            payment_type="credits",
            amount=Decimal("9.99"),
            currency="USD",
            status="pending",
            metadata_json=json.dumps({"credits": 500}),
        )
        self.session.add(payment)
        self.session.commit()

        result = _process_payment_update(
            self.session, payment, "paid", "evt_1", "mercadopago",
            verified_amount=Decimal("9.99"), verified_currency="USD",
        )
        self.session.commit()

        self.assertTrue(result)
        self.assertEqual(payment.status, "paid")
        self.assertIsNotNone(payment.completed_at)

        self.session.refresh(self.tenant)
        self.assertEqual(self.tenant.ai_credits, 600)  # 100 + 500

    def test_amount_mismatch_rejected(self):
        from routers.webhooks import _process_payment_update

        payment = PlatformPayment(
            tenant_id=self.tenant.id,
            provider="stripe",
            external_id="cs_abc",
            payment_type="credits",
            amount=Decimal("9.99"),
            currency="USD",
            status="pending",
            metadata_json=json.dumps({"credits": 500}),
        )
        self.session.add(payment)
        self.session.commit()

        result = _process_payment_update(
            self.session, payment, "paid", "evt_2", "stripe",
            verified_amount=Decimal("1.00"), verified_currency="USD",
        )
        self.assertFalse(result)
        self.assertEqual(payment.status, "pending")

    def test_currency_mismatch_rejected(self):
        from routers.webhooks import _process_payment_update

        payment = PlatformPayment(
            tenant_id=self.tenant.id,
            provider="mercadopago",
            external_id="mp_100",
            payment_type="credits",
            amount=Decimal("9.99"),
            currency="USD",
            status="pending",
            metadata_json=json.dumps({"credits": 100}),
        )
        self.session.add(payment)
        self.session.commit()

        result = _process_payment_update(
            self.session, payment, "paid", "evt_3", "mercadopago",
            verified_amount=Decimal("9.99"), verified_currency="ARS",
        )
        self.assertFalse(result)

    def test_paid_to_refunded_returns_stock(self):
        from routers.webhooks import _process_payment_update

        loc = Location(tenant_id=self.tenant.id, name="Default")
        self.session.add(loc)
        self.session.commit()

        bin_ = Bin(tenant_id=self.tenant.id, location_id=loc.id, name="A1")
        self.session.add(bin_)
        self.session.commit()

        product = Product(tenant_id=self.tenant.id, name="Widget", barcode="TEST001", price=Decimal("50"))
        self.session.add(product)
        self.session.commit()

        bin_stock = BinStock(
            tenant_id=self.tenant.id,
            bin_id=bin_.id,
            product_id=product.id,
            quantity=5,
        )
        self.session.add(bin_stock)

        sale = Sale(
            tenant_id=self.tenant.id,
            total_amount=Decimal("100"),
            payment_status="pagado",
        )
        self.session.add(sale)
        self.session.commit()

        item = SaleItem(
            sale_id=sale.id,
            product_id=product.id,
            product_name="Widget",
            quantity=2,
            unit_price=Decimal("50"),
            total=Decimal("100"),
        )
        self.session.add(item)
        self.session.commit()

        payment = PlatformPayment(
            tenant_id=self.tenant.id,
            provider="mercadopago",
            external_id="mp_200",
            payment_type="storefront_checkout",
            amount=Decimal("100"),
            currency="USD",
            status="paid",
            sale_id=sale.id,
        )
        self.session.add(payment)
        self.session.commit()

        result = _process_payment_update(
            self.session, payment, "refunded", "evt_4", "mercadopago",
        )
        self.session.commit()

        self.assertTrue(result)
        self.assertEqual(payment.status, "refunded")

        self.session.refresh(sale)
        self.assertEqual(sale.payment_status, "reembolsado")

        self.session.refresh(bin_stock)
        self.assertEqual(bin_stock.quantity, 7)  # 5 + 2 returned

    def test_plan_upgrade_via_webhook(self):
        from routers.webhooks import _process_payment_update

        payment = PlatformPayment(
            tenant_id=self.tenant.id,
            provider="mercadopago",
            external_id="mp_plan_1",
            payment_type="subscription",
            amount=Decimal("19.00"),
            currency="USD",
            status="pending",
            metadata_json=json.dumps({"plan": "tienda", "credits": 500}),
        )
        self.session.add(payment)
        self.session.commit()

        _process_payment_update(
            self.session, payment, "paid", "evt_5", "mercadopago",
            verified_amount=Decimal("19.00"), verified_currency="USD",
        )
        self.session.commit()

        self.session.refresh(self.tenant)
        self.assertEqual(self.tenant.ai_tier, "tienda")
        self.assertEqual(self.tenant.ai_credits, 600)  # 100 + 500

    def test_other_tenant_payment_not_affected(self):
        """Webhook con external_ref de otro tenant no procesa."""
        from routers.webhooks import _process_payment_update

        tenant2 = Tenant(name="T2", subdomain="t2", nivel=1, ai_credits=50)
        self.session.add(tenant2)
        self.session.commit()

        payment_t2 = PlatformPayment(
            tenant_id=tenant2.id,
            provider="mercadopago",
            external_id="mp_t2",
            payment_type="credits",
            amount=Decimal("9.99"),
            currency="USD",
            status="pending",
            metadata_json=json.dumps({"credits": 500}),
        )
        self.session.add(payment_t2)
        self.session.commit()

        _process_payment_update(
            self.session, payment_t2, "paid", "evt_t2", "mercadopago",
            verified_amount=Decimal("9.99"), verified_currency="USD",
        )
        self.session.commit()

        self.session.refresh(self.tenant)
        self.assertEqual(self.tenant.ai_credits, 100)  # unchanged

        self.session.refresh(tenant2)
        self.assertEqual(tenant2.ai_credits, 550)  # 50 + 500


class TestCommission(unittest.TestCase):
    def test_commission_calculation(self):
        from routers.payments import _calc_commission
        tenant = MagicMock()
        tenant.platform_commission_pct = Decimal("5.00")
        self.assertEqual(_calc_commission(tenant, Decimal("100.00")), Decimal("5.00"))
        self.assertEqual(_calc_commission(tenant, Decimal("49.90")), Decimal("2.50"))

    def test_commission_custom_pct(self):
        from routers.payments import _calc_commission
        tenant = MagicMock()
        tenant.platform_commission_pct = Decimal("3.50")
        self.assertEqual(_calc_commission(tenant, Decimal("200.00")), Decimal("7.00"))


class TestExternalRef(unittest.TestCase):
    def test_ref_is_uuid_hex(self):
        from routers.payments import _make_ref
        ref = _make_ref()
        self.assertEqual(len(ref), 32)
        int(ref, 16)  # valid hex

    def test_refs_are_unique(self):
        from routers.payments import _make_ref
        refs = {_make_ref() for _ in range(100)}
        self.assertEqual(len(refs), 100)


class TestMerchantTokenRequired(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()

    def test_no_config_returns_none(self):
        from routers.payments import _get_merchant_token
        tenant = Tenant(name="T1", subdomain="t1", nivel=1)
        self.session.add(tenant)
        self.session.commit()
        self.assertIsNone(_get_merchant_token(self.session, tenant.id, "mercadopago"))


class TestStripeWebhookSignature(unittest.TestCase):
    def test_valid_signature_accepted(self):
        from services.payment_service import StripeProvider
        provider = StripeProvider()
        provider.webhook_secret = "whsec_test123"

        payload = json.dumps({"id": "evt_1", "type": "checkout.session.completed"})
        ts = str(int(time.time()))
        signed = f"{ts}.{payload}"
        sig = hmac.HMAC(b"whsec_test123", signed.encode(), hashlib.sha256).hexdigest()

        headers = {"stripe-signature": f"t={ts},v1={sig}"}
        result = provider.verify_webhook(headers, payload.encode())
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "evt_1")

    def test_invalid_signature_rejected(self):
        from services.payment_service import StripeProvider
        provider = StripeProvider()
        provider.webhook_secret = "whsec_test123"

        payload = b'{"id":"evt_1"}'
        headers = {"stripe-signature": "t=12345,v1=invalid"}
        result = provider.verify_webhook(headers, payload)
        self.assertIsNone(result)

    def test_expired_timestamp_rejected(self):
        from services.payment_service import StripeProvider
        provider = StripeProvider()
        provider.webhook_secret = "whsec_test123"

        payload = b'{"id":"evt_1"}'
        ts = str(int(time.time()) - 600)
        signed = f"{ts}.{payload.decode()}"
        sig = hmac.HMAC(b"whsec_test123", signed.encode(), hashlib.sha256).hexdigest()

        headers = {"stripe-signature": f"t={ts},v1={sig}"}
        result = provider.verify_webhook(headers, payload)
        self.assertIsNone(result)


class TestMercadoPagoProvider(unittest.TestCase):
    def test_is_configured(self):
        from services.payment_service import MercadoPagoProvider
        p = MercadoPagoProvider()
        p.platform_token = ""
        self.assertFalse(p.is_configured())
        p.platform_token = "TEST-token"
        self.assertTrue(p.is_configured())

    def test_status_mapping(self):
        from routers.webhooks import _map_status
        self.assertEqual(_map_status("COMPLETED"), "paid")
        self.assertEqual(_map_status("PENDING"), "pending")
        self.assertEqual(_map_status("FAILED"), "failed")
        self.assertEqual(_map_status("CANCELLED"), "cancelled")
        self.assertEqual(_map_status("REFUNDED"), "refunded")
        self.assertEqual(_map_status("CHARGED_BACK"), "charged_back")
        self.assertEqual(_map_status("UNKNOWN"), "failed")


class TestTenantPaymentConfigModel(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()

    def test_create_config(self):
        tenant = Tenant(name="T1", subdomain="t1", nivel=1)
        self.session.add(tenant)
        self.session.commit()

        config = TenantPaymentConfig(
            tenant_id=tenant.id,
            provider="mercadopago",
            access_token_enc=encrypt_api_key("TEST-token-mp"),
            merchant_id="12345",
        )
        self.session.add(config)
        self.session.commit()

        loaded = self.session.exec(
            select(TenantPaymentConfig).where(
                TenantPaymentConfig.tenant_id == tenant.id,
            )
        ).first()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.provider, "mercadopago")
        self.assertTrue(loaded.is_active)


if __name__ == "__main__":
    unittest.main()
