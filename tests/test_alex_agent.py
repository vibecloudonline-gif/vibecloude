"""Tests for AlexAgentContext and dynamic prompt building (Fase 3)."""
import os
os.environ.setdefault("SECRET_KEY", "testsecretkey123")
os.environ.setdefault("VIBECLOUD_FERNET_KEY", "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI=")

import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from database.models import AlexAgentContext, Offer, Tenant, User, Settings
from database.session import get_session
from main import app
from services.auth_service import AuthService


def _create_user(session, username, password, tenant_id, role="admin"):
    user = User(
        username=username,
        password_hash=AuthService.get_password_hash(password),
        role=role,
        tenant_id=tenant_id,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


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


def _make_tenant_with_admin(session, has_alexio=True):
    tenant = Tenant(name="AgentTest", subdomain="agenttest", has_alexio=has_alexio, has_landing=True)
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    user = _create_user(session, "admin", "TestPass123!", tenant.id, role="admin")
    settings = Settings(tenant_id=tenant.id, company_name="AgentTest")
    session.add(settings)
    session.commit()
    return tenant, user


def test_alex_agent_page_accessible(client, session):
    tenant, user = _make_tenant_with_admin(session)
    client.post("/login", data={"username": "admin", "password": "TestPass123!"}, follow_redirects=False)
    resp = client.get("/panel/alex-agent")
    assert resp.status_code == 200


def test_save_agent_context(client, session):
    tenant, user = _make_tenant_with_admin(session)
    client.post("/login", data={"username": "admin", "password": "TestPass123!"}, follow_redirects=False)
    resp = client.post("/panel/alex-agent/guardar", data={
        "personality_tone": "casual",
        "business_description": "Vendemos cosas lindas",
        "validated_offer_id": "",
        "custom_instructions": "No hablar de la competencia",
        "faq_json": json.dumps([{"q": "Hacen envios?", "a": "Si, a todo el pais"}]),
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


def test_dynamic_prompt_fallback_when_no_context(session):
    from services.ai_brain_service import AIBrainService
    tenant = Tenant(name="Empty", subdomain="empty", has_alexio=True)
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    result = AIBrainService.build_dynamic_prompt(session, tenant.id)
    assert result is None


def test_agent_gated_by_alexio_flag(client, session):
    tenant, user = _make_tenant_with_admin(session, has_alexio=False)
    client.post("/login", data={"username": "admin", "password": "TestPass123!"}, follow_redirects=False)
    resp = client.get("/panel/alex-agent")
    assert resp.status_code == 403
