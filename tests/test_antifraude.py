import os
os.environ["SECRET_KEY"] = "testsecretkey123"
os.environ["VIBECLOUD_API_KEY"] = "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI="

import pytest
from decimal import Decimal

from database.models import (
    OrderFingerprint, ReturnRequest, TrustMetrics,
    BusinessReview, Sale, Tenant,
)
from services.trust_service import calculate_commission


def test_orderfingerprint_fields():
    fp = OrderFingerprint(
        sale_id=1, tenant_id=1,
        buyer_ip="192.168.1.1",
        buyer_user_agent="Mozilla/5.0",
        buyer_device_hash="abc123",
    )
    assert fp.buyer_ip == "192.168.1.1"
    assert fp.is_self_purchase is False
    assert fp.fraud_score == 0
    assert fp.fraud_reasons is None


def test_returnrequest_fields():
    rr = ReturnRequest(
        tenant_id=1, sale_id=1,
        reason="defective", detail="Product arrived broken",
    )
    assert rr.status == "pending"
    assert rr.refund_amount is None
    assert rr.resolved_at is None


def test_trustmetrics_defaults():
    tm = TrustMetrics(tenant_id=1)
    assert tm.total_sales == 0
    assert tm.unique_buyers == 0
    assert tm.return_rate_pct == Decimal("0.00")
    assert tm.self_purchase_count == 0


def test_sale_commission_fields():
    s = Sale(tenant_id=1, total_amount=Decimal("100.00"))
    assert s.platform_commission == Decimal("0.00")
    assert s.fraud_flag is None


def test_tenant_commission_pct():
    t = Tenant(name="Test", subdomain="test")
    assert t.platform_commission_pct == Decimal("5.00")


def test_calculate_commission():
    assert calculate_commission(Decimal("100.00"), Decimal("5.00")) == Decimal("5.00")
    assert calculate_commission(Decimal("250.00"), Decimal("10.00")) == Decimal("25.00")
    assert calculate_commission(Decimal("0.00"), Decimal("5.00")) == Decimal("0.00")
    assert calculate_commission(Decimal("33.33"), Decimal("7.50")) == Decimal("2.50")


def test_review_verified_purchase_field():
    r = BusinessReview(
        profile_id=1, reviewer_tenant_id=2, rating=5,
    )
    assert r.is_verified_purchase is False


def test_returnrequest_statuses():
    for status in ("pending", "approved", "rejected", "refunded"):
        rr = ReturnRequest(tenant_id=1, sale_id=1, reason="test", status=status)
        assert rr.status == status


def test_orderfingerprint_self_purchase_flag():
    fp = OrderFingerprint(
        sale_id=1, tenant_id=1,
        is_self_purchase=True, fraud_score=50,
        fraud_reasons="cuit_match_owner,repeated_device",
    )
    assert fp.is_self_purchase is True
    assert fp.fraud_score == 50
    assert "cuit_match_owner" in fp.fraud_reasons


def test_trustmetrics_return_rate():
    tm = TrustMetrics(
        tenant_id=1,
        total_sales=100,
        return_count=5,
        return_rate_pct=Decimal("5.00"),
    )
    assert tm.return_rate_pct == Decimal("5.00")


def test_trust_service_endpoints_exist():
    from routers.network import router
    routes = [r.path for r in router.routes]
    assert "/panel/red/review/{profile_id}" in routes
