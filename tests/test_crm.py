"""Tests for the CRM integration module."""
import os
os.environ.setdefault("SECRET_KEY", "testsecretkey123")
os.environ.setdefault("VIBECLOUD_API_KEY", "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI=")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from database.models import (
    AICredential, Client, Sale, CRMSyncLog, Settings, Tenant, User,
    encrypt_api_key,
)
from database.session import get_session
from main import app
from services.auth_service import AuthService


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def client(session):
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    from core.limiter import limiter, HAS_SLOWAPI
    if HAS_SLOWAPI:
        limiter.reset()
    yield


def _make_tenant(session):
    tenant = Tenant(name="TestCRM", subdomain="testcrm", has_landing=True, has_ecommerce=True, nivel=3)
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    user = User(
        username="admin", role="admin", tenant_id=tenant.id,
        password_hash=AuthService.get_password_hash("TestPass123!"),
    )
    session.add(user)
    settings = Settings(tenant_id=tenant.id, company_name="TestCRM")
    session.add(settings)
    session.commit()
    session.refresh(user)
    return tenant, user


def _login(client):
    client.post("/login", data={"username": "admin", "password": "TestPass123!"}, follow_redirects=False)


# --- Panel ---

def test_crm_dashboard_accessible(client, session):
    _make_tenant(session)
    _login(client)
    resp = client.get("/panel/crm")
    assert resp.status_code == 200
    assert "Integración CRM" in resp.text


def test_crm_dashboard_shows_not_configured(client, session):
    _make_tenant(session)
    _login(client)
    resp = client.get("/panel/crm")
    assert "Pendiente" in resp.text


def test_crm_save_config(client, session):
    tenant, user = _make_tenant(session)
    _login(client)
    resp = client.post("/panel/crm/config", data={
        "crm_base_url": "https://api.mycrm.com",
        "crm_api_key": "sk-test-12345",
    }, follow_redirects=False)
    assert resp.status_code == 302
    cred = session.exec(
        select(AICredential).where(
            AICredential.tenant_id == tenant.id,
            AICredential.provider == "crm",
        )
    ).first()
    assert cred is not None
    settings = session.exec(select(Settings).where(Settings.tenant_id == tenant.id)).first()
    import json
    cfg = json.loads(settings.site_config_json)
    assert cfg["crm_base_url"] == "https://api.mycrm.com"


def test_crm_sync_without_config(client, session):
    _make_tenant(session)
    _login(client)
    resp = client.post("/panel/crm/sync", data={"sync_type": "full"})
    assert resp.status_code == 400


# --- Models ---

def test_crm_external_id_on_client(session):
    tenant = Tenant(name="T", subdomain="t")
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    cl = Client(tenant_id=tenant.id, name="Test Client", crm_external_id="ext-123")
    session.add(cl)
    session.commit()
    session.refresh(cl)
    assert cl.crm_external_id == "ext-123"


def test_crm_external_id_on_sale(session):
    tenant = Tenant(name="T", subdomain="t")
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    sale = Sale(tenant_id=tenant.id, crm_external_id="deal-456")
    session.add(sale)
    session.commit()
    session.refresh(sale)
    assert sale.crm_external_id == "deal-456"


def test_sync_log_model(session):
    tenant = Tenant(name="T", subdomain="t")
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    log = CRMSyncLog(
        tenant_id=tenant.id, sync_type="full", direction="bidirectional",
        status="completed", contacts_synced=10, sales_synced=5,
    )
    session.add(log)
    session.commit()
    session.refresh(log)
    assert log.contacts_synced == 10
    assert log.status == "completed"


def test_crm_log_page(client, session):
    _make_tenant(session)
    _login(client)
    resp = client.get("/panel/crm/log")
    assert resp.status_code == 200


# --- Multiple AICredentials per tenant ---

def test_multiple_credentials_per_tenant(session):
    tenant = Tenant(name="T", subdomain="t")
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    cred_gemini = AICredential(
        tenant_id=tenant.id, provider="gemini",
        api_key_enc=encrypt_api_key("gemini-key"),
    )
    cred_crm = AICredential(
        tenant_id=tenant.id, provider="crm",
        api_key_enc=encrypt_api_key("crm-key"),
    )
    session.add_all([cred_gemini, cred_crm])
    session.commit()
    all_creds = session.exec(
        select(AICredential).where(AICredential.tenant_id == tenant.id)
    ).all()
    assert len(all_creds) == 2
    providers = {c.provider for c in all_creds}
    assert providers == {"gemini", "crm"}
