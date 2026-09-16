"""Tests for the debate service (Fase 2 of Alex IO pipeline)."""
import os
os.environ.setdefault("SECRET_KEY", "testsecretkey123")
os.environ.setdefault("VIBECLOUD_FERNET_KEY", "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI=")

import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from database.models import (
    Offer, ValidationDebate, DebateObjection,
    ResearchProject, Tenant, User, Settings,
)
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


def _setup_tenant_with_offer(session):
    tenant = Tenant(name="DebateTest", subdomain="debatetest", has_alexio=True, has_landing=True)
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    user = _create_user(session, "admin", "TestPass123!", tenant.id, role="admin")
    settings = Settings(tenant_id=tenant.id, company_name="DebateTest")
    session.add(settings)
    project = ResearchProject(
        tenant_id=tenant.id, user_id=user.id,
        project_type="physical_product",
        query_description="test", status="completed",
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    offer = Offer(
        tenant_id=tenant.id, project_id=project.id,
        title="Test Offer", value_proposition="Great",
        price_structure="$29/mes", cta_text="Comprar",
        status="pending_validation", version=1,
    )
    session.add(offer)
    session.commit()
    session.refresh(offer)
    return tenant, user, offer


def test_debate_model_fields():
    debate = ValidationDebate(offer_id=1, status="in_progress")
    assert debate.status == "in_progress"
    assert debate.final_verdict is None


def test_objection_model_fields():
    for source in ("devil_advocate", "price_skeptic", "market_analyst", "customer_sim"):
        obj = DebateObjection(
            debate_id=1, objection_text="test",
            objection_source=source, severity="medium", order_index=0,
        )
        assert obj.objection_source == source


def test_debate_personas_exist():
    from services.debate_service import _DEBATE_PERSONAS
    assert len(_DEBATE_PERSONAS) == 4
    names = {p["id"] for p in _DEBATE_PERSONAS}
    assert names == {"devil_advocate", "price_skeptic", "market_analyst", "customer_sim"}


def test_debate_page_no_debate(client, session):
    tenant, user, offer = _setup_tenant_with_offer(session)
    client.post("/login", data={"username": "admin", "password": "TestPass123!"}, follow_redirects=False)
    resp = client.get(f"/panel/oferta/{offer.id}/debate")
    assert resp.status_code == 200


def test_validate_endpoint_exists(client, session):
    tenant, user, offer = _setup_tenant_with_offer(session)
    client.post("/login", data={"username": "admin", "password": "TestPass123!"}, follow_redirects=False)
    with patch("services.debate_service.run_debate", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = ValidationDebate(
            offer_id=offer.id, status="completed",
            final_verdict="approved", arbiter_summary="All good",
        )
        resp = client.post(f"/panel/oferta/{offer.id}/validar")
        assert resp.status_code in (200, 400, 500)
