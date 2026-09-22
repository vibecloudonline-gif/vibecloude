import os
os.environ["SECRET_KEY"] = "testsecretkey123"
os.environ["VIBECLOUD_API_KEY"] = "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI="
os.environ["PAYPAL_CLIENT_ID"] = "test_client_id"
os.environ["PAYPAL_CLIENT_SECRET"] = "test_client_secret"

import json
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from database.models import PlatformPayment, Sale, SaleItem, Settings, Tenant, User
from database.session import get_session
from main import app
from services.auth_service import AuthService
from services.payment_service import (
    CaptureResult,
    PaymentResult,
    PayPalProvider,
    StripeProvider,
    PROVIDERS,
)


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def tenant_and_user(session):
    tenant = Tenant(name="Test Shop", subdomain="testshop", ai_credits=100, ai_tier="free")
    session.add(tenant)
    session.flush()

    user = User(
        username="admin",
        password_hash=AuthService.get_password_hash("Test1234!"),
        role="admin",
        tenant_id=tenant.id,
    )
    session.add(user)

    settings = Settings(tenant_id=tenant.id, business_name="Test Shop")
    session.add(settings)
    session.commit()
    return tenant, user


@pytest.fixture
def client(session):
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def authed_client(client, tenant_and_user):
    tenant, user = tenant_and_user
    client.post("/login", data={"username": "admin", "password": "Test1234!"})
    return client, tenant


MOCK_PAYPAL_CREATE = PaymentResult(
    external_id="PAYPAL-ORDER-123",
    approve_url="https://www.sandbox.paypal.com/checkoutnow?token=PAYPAL-ORDER-123",
    status="CREATED",
    raw={"id": "PAYPAL-ORDER-123", "status": "CREATED"},
)

MOCK_PAYPAL_CAPTURE_OK = CaptureResult(
    external_id="PAYPAL-ORDER-123",
    status="COMPLETED",
    raw={"id": "PAYPAL-ORDER-123", "status": "COMPLETED"},
)

MOCK_PAYPAL_CAPTURE_FAIL = CaptureResult(
    external_id="PAYPAL-ORDER-123",
    status="VOIDED",
    raw={"id": "PAYPAL-ORDER-123", "status": "VOIDED"},
)


@pytest.fixture(autouse=True)
def mock_paypal_provider():
    mock = AsyncMock(spec=PayPalProvider)
    mock.create_order = AsyncMock(return_value=MOCK_PAYPAL_CREATE)
    mock.capture_order = AsyncMock(return_value=MOCK_PAYPAL_CAPTURE_OK)
    mock.is_configured = lambda: True
    old = PROVIDERS.get("paypal")
    PROVIDERS["paypal"] = mock
    yield mock
    if old:
        PROVIDERS["paypal"] = old
    else:
        PROVIDERS.pop("paypal", None)


# ── Créditos ────────────────────────────────────────────────────────────────

def test_create_credits_order(authed_client, session):
    client, tenant = authed_client
    resp = client.post(
        "/api/v1/payments/credits/create",
        json={"credits": 100, "provider": "paypal"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "sandbox.paypal.com" in data["approve_url"]
    assert data["external_id"] == "PAYPAL-ORDER-123"

    payment = session.exec(select(PlatformPayment).where(PlatformPayment.tenant_id == tenant.id)).first()
    assert payment is not None
    assert payment.payment_type == "credits"
    assert payment.status == "pending"
    assert payment.amount == Decimal("2.99")


def test_create_credits_invalid_pack(authed_client):
    client, _ = authed_client
    resp = client.post(
        "/api/v1/payments/credits/create",
        json={"credits": 999, "provider": "paypal"},
    )
    assert resp.status_code == 400


def test_capture_credits_adds_credits(authed_client, session):
    client, tenant = authed_client

    client.post("/api/v1/payments/credits/create", json={"credits": 500, "provider": "paypal"})

    resp = client.get(
        "/payments/credits/capture?token=PAYPAL-ORDER-123&provider=paypal",
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "status=success" in resp.headers["location"]
    assert "credits=500" in resp.headers["location"]

    session.refresh(tenant)
    assert tenant.ai_credits == 600  # 100 original + 500


def test_capture_credits_failed(authed_client, session, mock_paypal_provider):
    client, tenant = authed_client
    client.post("/api/v1/payments/credits/create", json={"credits": 100, "provider": "paypal"})

    mock_paypal_provider.capture_order = AsyncMock(return_value=MOCK_PAYPAL_CAPTURE_FAIL)

    resp = client.get(
        "/payments/credits/capture?token=PAYPAL-ORDER-123&provider=paypal",
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "status=failed" in resp.headers["location"]

    session.refresh(tenant)
    assert tenant.ai_credits == 100  # sin cambio


def test_capture_credits_idempotent(authed_client, session):
    client, tenant = authed_client
    client.post("/api/v1/payments/credits/create", json={"credits": 100, "provider": "paypal"})

    client.get("/payments/credits/capture?token=PAYPAL-ORDER-123&provider=paypal", follow_redirects=False)
    resp = client.get("/payments/credits/capture?token=PAYPAL-ORDER-123&provider=paypal", follow_redirects=False)
    assert "already_completed" in resp.headers["location"]

    session.refresh(tenant)
    assert tenant.ai_credits == 200  # solo se sumó una vez


# ── Planes ──────────────────────────────────────────────────────────────────

def test_create_plan_order(authed_client, session):
    client, tenant = authed_client
    resp = client.post(
        "/api/v1/payments/plan/create",
        json={"plan": "starter", "provider": "paypal"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True

    payment = session.exec(
        select(PlatformPayment).where(
            PlatformPayment.tenant_id == tenant.id,
            PlatformPayment.payment_type == "plan_upgrade",
        )
    ).first()
    assert payment is not None
    assert payment.amount == Decimal("15.00")


def test_plan_upgrade_already_on_plan(authed_client, session):
    client, tenant = authed_client
    tenant.ai_tier = "starter"
    session.add(tenant)
    session.commit()

    resp = client.post(
        "/api/v1/payments/plan/create",
        json={"plan": "starter", "provider": "paypal"},
    )
    assert resp.status_code == 400


def test_capture_plan_upgrades_tenant(authed_client, session):
    client, tenant = authed_client
    client.post("/api/v1/payments/plan/create", json={"plan": "growth", "provider": "paypal"})

    resp = client.get(
        "/payments/plan/capture?token=PAYPAL-ORDER-123&provider=paypal",
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "status=success" in resp.headers["location"]

    session.refresh(tenant)
    assert tenant.ai_tier == "growth"
    assert tenant.ai_credits == 2100  # 100 original + 2000 de growth


# ── Storefront checkout ─────────────────────────────────────────────────────

def test_storefront_checkout_payment(session, client, tenant_and_user, mock_paypal_provider):
    tenant, user = tenant_and_user
    sale = Sale(
        tenant_id=tenant.id,
        total_amount=Decimal("50.00"),
        payment_status="pendiente",
    )
    session.add(sale)
    session.commit()
    session.refresh(sale)

    resp = client.post(
        "/tienda/checkout/pagar",
        data={"sale_id": str(sale.id), "provider": "paypal"},
        headers={"host": "testshop.vibecloud.com"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "sandbox.paypal.com" in resp.headers["location"]

    payment = session.exec(
        select(PlatformPayment).where(PlatformPayment.sale_id == sale.id)
    ).first()
    assert payment is not None
    assert payment.payment_type == "storefront_checkout"
    assert payment.amount == Decimal("50.00")


def test_storefront_capture_marks_sale_paid(session, client, tenant_and_user, mock_paypal_provider):
    tenant, user = tenant_and_user
    sale = Sale(
        tenant_id=tenant.id,
        total_amount=Decimal("25.00"),
        payment_status="pendiente",
    )
    session.add(sale)
    session.commit()
    session.refresh(sale)

    payment = PlatformPayment(
        tenant_id=tenant.id,
        provider="paypal",
        external_id="PAYPAL-ORDER-123",
        payment_type="storefront_checkout",
        amount=Decimal("25.00"),
        status="pending",
        sale_id=sale.id,
    )
    session.add(payment)
    session.commit()

    resp = client.get(
        f"/tienda/checkout/capturar?sale_id={sale.id}&token=PAYPAL-ORDER-123&provider=paypal",
        headers={"host": "testshop.vibecloud.com"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "status=paid" in resp.headers["location"]

    session.refresh(sale)
    assert sale.payment_status == "pagado"


# ── Info endpoints ──────────────────────────────────────────────────────────

def test_list_providers(client):
    resp = client.get("/api/v1/payments/providers")
    assert resp.status_code == 200
    assert "paypal" in resp.json()["providers"]


def test_list_credit_packs(client):
    resp = client.get("/api/v1/payments/credits/packs")
    assert resp.status_code == 200
    packs = resp.json()["packs"]
    assert "100" in packs
    assert "500" in packs


def test_list_plans(client):
    resp = client.get("/api/v1/payments/plans")
    assert resp.status_code == 200
    plans = resp.json()["plans"]
    assert "starter" in plans
    assert "growth" in plans
    assert plans["starter"]["price"] == "15.00"
