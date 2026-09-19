import asyncio
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from database.models import ResearchForecast, ResearchProject, Settings, Tenant, User
from database.session import get_session
from main import app
from services.auth_service import AuthService
from services.timesfm_provider import (
    _analytical_fallback,
    _build_price_series,
    generate_market_forecast,
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
def client(session):
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _create_user(session: Session, username: str, password: str, tenant_id: int, role: str = "admin") -> User:
    hashed = AuthService.get_password_hash(password)
    user = User(username=username, password_hash=hashed, role=role, tenant_id=tenant_id, is_active=True)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _make_tenant_with_admin(session):
    tenant = Tenant(name="TestTenant", subdomain="test-timesfm", has_alexio=True, has_landing=True, has_ecommerce=True)
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    user = _create_user(session, "timesfm_admin", "TestPass123!", tenant.id, role="admin")
    settings = Settings(tenant_id=tenant.id, company_name="Test")
    session.add(settings)
    session.commit()
    return tenant, user


def test_build_price_series_length_and_anchor():
    prices = [25.0, 30.0, 35.0]
    series = _build_price_series(prices, n_points=16)
    assert len(series) == 16
    assert series[-1] == 30.0  # average of 25, 30, 35
    assert all(p > 0 for p in series)


def test_analytical_fallback_forecast_structure():
    price_series = [20.0, 22.0, 25.0, 28.0, 30.0]
    result = _analytical_fallback("Smartwatch fitness", price_series, horizon_days=30)
    assert len(result.forecast_series) >= 4
    assert len(result.confidence_low) == len(result.forecast_series)
    assert len(result.confidence_high) == len(result.forecast_series)
    assert result.trend_direction in ("alcista", "bajista", "estable")
    assert result.trend_direction == "alcista"  # positive slope
    assert "Smartwatch fitness" in result.recommendation


def test_generate_market_forecast_async():
    prices = [49.99, 55.0, 42.50, 60.0]
    result = asyncio.run(generate_market_forecast("Auriculares bluetooth", prices, horizon_days=30))
    assert result is not None
    assert len(result.forecast_series) > 0
    assert result.provider in ("timesfm_api", "gemini_forecast", "timesfm_simulated")


def test_forecast_endpoints_flow(client, session):
    tenant, user = _make_tenant_with_admin(session)
    client.post("/login", data={"username": "timesfm_admin", "password": "TestPass123!"}, follow_redirects=False)

    # 1. Crear proyecto
    create_resp = client.post("/panel/research/nuevo", data={
        "project_type": "physical_product",
        "query_description": "mochila impermeable para laptop",
        "reference_url": "",
        "factory_price": "20.00",
    })
    assert create_resp.status_code == 200
    pid = create_resp.json()["project_id"]

    # 2. Ejecutar busqueda para tener listings
    search_resp = client.post(f"/panel/research/{pid}/buscar")
    assert search_resp.status_code == 200

    # 3. Generar forecast
    fc_resp = client.post(f"/panel/research/{pid}/forecast", data={"horizon_days": "30"})
    assert fc_resp.status_code == 200
    fc_data = fc_resp.json()
    assert fc_data["status"] == "success"
    assert "forecast_id" in fc_data
    assert "trend_direction" in fc_data

    # 4. Ver panel HTML de forecast
    view_resp = client.get(f"/panel/forecast/{pid}")
    assert view_resp.status_code == 200
    assert "Forecast de Mercado" in view_resp.text
    assert "mochila impermeable" in view_resp.text


def test_forecast_view_requires_auth():
    fresh_client = TestClient(app)
    resp = fresh_client.get("/panel/forecast/1", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("location", "")
