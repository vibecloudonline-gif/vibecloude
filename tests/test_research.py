"""Tests for the research module (Fase 1 of Alex IO pipeline)."""
import os
os.environ.setdefault("SECRET_KEY", "testsecretkey123")
os.environ.setdefault("VIBECLOUD_FERNET_KEY", "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI=")

import asyncio
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from database.models import ResearchProject, Tenant, User, Settings
from database.session import get_session
from main import app
from services.auth_service import AuthService
from services.research_providers.mock_provider import MockProvider


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
    tenant = Tenant(name="TestTenant", subdomain="test", has_alexio=has_alexio, has_landing=True, has_ecommerce=True)
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    user = _create_user(session, "admin", "TestPass123!", tenant.id, role="admin")
    settings = Settings(tenant_id=tenant.id, company_name="Test")
    session.add(settings)
    session.commit()
    return tenant, user


def test_research_dashboard_accessible(client, session):
    tenant, user = _make_tenant_with_admin(session)
    client.post("/login", data={"username": "admin", "password": "TestPass123!"}, follow_redirects=False)
    resp = client.get("/panel/research")
    assert resp.status_code == 200


def test_create_project(client, session):
    tenant, user = _make_tenant_with_admin(session)
    client.post("/login", data={"username": "admin", "password": "TestPass123!"}, follow_redirects=False)
    resp = client.post("/panel/research/nuevo", data={
        "project_type": "physical_product",
        "query_description": "auriculares bluetooth deportivos",
        "reference_url": "",
        "factory_price": "15.00",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "project_id" in data


def test_create_project_empty_description_rejected(client, session):
    tenant, user = _make_tenant_with_admin(session)
    client.post("/login", data={"username": "admin", "password": "TestPass123!"}, follow_redirects=False)
    resp = client.post("/panel/research/nuevo", data={
        "project_type": "physical_product",
        "query_description": "  ",
        "reference_url": "",
        "factory_price": "",
    })
    assert resp.status_code == 400


def test_mock_provider_deterministic():
    provider = MockProvider()
    result1 = asyncio.run(provider.search_products("test query"))
    result2 = asyncio.run(provider.search_products("test query"))
    assert len(result1) >= 3
    assert len(result1) == len(result2)
    assert result1[0].title == result2[0].title
    assert all(r.is_demo for r in result1)


def test_mock_provider_demand_always_bajo():
    provider = MockProvider()
    demand = asyncio.run(provider.estimate_demand("test"))
    assert demand.confidence_level == "bajo"


def test_project_detail_requires_auth():
    fresh_client = TestClient(app)
    resp = fresh_client.get("/panel/research/1", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("location", "")
