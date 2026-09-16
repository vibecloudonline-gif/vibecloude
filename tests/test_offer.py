"""Tests for the offer service (Fase 2 of Alex IO pipeline)."""
import os
os.environ.setdefault("SECRET_KEY", "testsecretkey123")
os.environ.setdefault("VIBECLOUD_FERNET_KEY", "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI=")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from database.models import ResearchProject, Offer, Tenant, User, Settings
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


def _setup_tenant_with_project(session, project_status="completed"):
    tenant = Tenant(name="OfferTest", subdomain="offertest", has_alexio=True, has_landing=True, has_ecommerce=True)
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    user = _create_user(session, "admin", "TestPass123!", tenant.id, role="admin")
    settings = Settings(tenant_id=tenant.id, company_name="OfferTest")
    session.add(settings)
    project = ResearchProject(
        tenant_id=tenant.id, user_id=user.id,
        project_type="physical_product",
        query_description="test product",
        status=project_status,
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return tenant, user, project


def test_offer_model_fields():
    offer = Offer(
        tenant_id=1, project_id=1,
        title="Test Offer", value_proposition="Great value",
        price_structure="$29/mo", cta_text="Buy Now",
        differentiators_json='["fast","cheap"]',
        status="draft", version=1,
    )
    assert offer.title == "Test Offer"
    assert offer.status == "draft"
    assert offer.version == 1


def test_offer_status_values():
    for status in ("draft", "pending_validation", "validated", "rejected"):
        offer = Offer(tenant_id=1, project_id=1, title="t", status=status, version=1)
        assert offer.status == status


def test_offer_page_no_offer(client, session):
    tenant, user, project = _setup_tenant_with_project(session)
    client.post("/login", data={"username": "admin", "password": "TestPass123!"}, follow_redirects=False)
    resp = client.get(f"/panel/oferta/{project.id}")
    assert resp.status_code == 200


def test_generate_requires_completed_project(client, session):
    tenant, user, project = _setup_tenant_with_project(session, project_status="draft")
    client.post("/login", data={"username": "admin", "password": "TestPass123!"}, follow_redirects=False)
    resp = client.post(f"/panel/oferta/{project.id}/generar")
    assert resp.status_code == 400
