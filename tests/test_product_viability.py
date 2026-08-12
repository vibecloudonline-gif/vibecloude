import os
os.environ["SECRET_KEY"] = "testsecretkey123"
os.environ["VIBECLOUD_FERNET_KEY"] = "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI="

import json
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from database.models import Product, Sale, SaleItem, Settings, Tenant, User
from database.session import get_session
from main import app
from services.ai_gateway_service import AIGatewayService, QwenClient
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


@pytest.fixture(autouse=True)
def ensure_qwen_unset(monkeypatch):
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    yield


def _make_tenant_with_admin(session, subdomain, username="admin", password="Contrasena123!"):
    tenant = Tenant(name=subdomain, subdomain=subdomain, has_erp=True)
    session.add(tenant)
    session.commit()
    session.refresh(tenant)

    session.add(Settings(tenant_id=tenant.id, company_name=subdomain))

    user = User(
        username=username,
        password_hash=AuthService.get_password_hash(password),
        role="admin",
        tenant_id=tenant.id,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return tenant, user


def _login(client, username, password="Contrasena123!"):
    return client.post("/login", data={"username": username, "password": password}, follow_redirects=False)


# ---------------------------------------------------------------------------
# _category_sales_context -- aislamiento por tenant + degradacion sin historial
# ---------------------------------------------------------------------------

def test_category_context_sin_historial(session):
    tenant, _ = _make_tenant_with_admin(session, "sin-historial")
    msg = AIGatewayService._category_sales_context(session, tenant.id, "Bebidas")
    assert "Sin ventas registradas" in msg


def test_category_context_sin_categoria(session):
    tenant, _ = _make_tenant_with_admin(session, "sin-categoria")
    msg = AIGatewayService._category_sales_context(session, tenant.id, None)
    assert "no tiene categoría" in msg


def test_category_context_usa_historial_real_y_lo_aisla_por_tenant(session):
    tenant_a, user_a = _make_tenant_with_admin(session, "tenant-a")
    tenant_b, _ = _make_tenant_with_admin(session, "tenant-b")

    product_a = Product(tenant_id=tenant_a.id, name="Coca Cola", barcode="111", category="Bebidas", price=Decimal("500"))
    product_b = Product(tenant_id=tenant_b.id, name="Coca Cola", barcode="111", category="Bebidas", price=Decimal("500"))
    session.add(product_a)
    session.add(product_b)
    session.commit()
    session.refresh(product_a)
    session.refresh(product_b)

    sale_a = Sale(tenant_id=tenant_a.id, total_amount=Decimal("5000"), timestamp=datetime.utcnow())
    session.add(sale_a)
    session.commit()
    session.refresh(sale_a)
    session.add(SaleItem(sale_id=sale_a.id, product_id=product_a.id, product_name="Coca Cola", quantity=10, unit_price=Decimal("500"), total=Decimal("5000")))

    # Venta de tenant B en la MISMA categoria -- no debe filtrarse al contexto de A.
    sale_b = Sale(tenant_id=tenant_b.id, total_amount=Decimal("50000"), timestamp=datetime.utcnow())
    session.add(sale_b)
    session.commit()
    session.refresh(sale_b)
    session.add(SaleItem(sale_id=sale_b.id, product_id=product_b.id, product_name="Coca Cola", quantity=100, unit_price=Decimal("500"), total=Decimal("50000")))
    session.commit()

    msg_a = AIGatewayService._category_sales_context(session, tenant_a.id, "Bebidas")
    assert "10 unidades" in msg_a
    assert "100 unidades" not in msg_a  # la venta de tenant B no se filtra

    msg_a_old = AIGatewayService._category_sales_context(session, tenant_a.id, "Bebidas")
    assert msg_a_old == msg_a


def test_category_context_ignora_ventas_viejas(session):
    tenant, _ = _make_tenant_with_admin(session, "ventas-viejas")
    product = Product(tenant_id=tenant.id, name="Agua", barcode="222", category="Bebidas", price=Decimal("300"))
    session.add(product)
    session.commit()
    session.refresh(product)

    old_sale = Sale(tenant_id=tenant.id, total_amount=Decimal("3000"), timestamp=datetime.utcnow() - timedelta(days=200))
    session.add(old_sale)
    session.commit()
    session.refresh(old_sale)
    session.add(SaleItem(sale_id=old_sale.id, product_id=product.id, product_name="Agua", quantity=10, unit_price=Decimal("300"), total=Decimal("3000")))
    session.commit()

    msg = AIGatewayService._category_sales_context(session, tenant.id, "Bebidas")
    assert "Sin ventas registradas" in msg  # fuera de la ventana de 90 dias


# ---------------------------------------------------------------------------
# predict_product_success -- disponible / no disponible
# ---------------------------------------------------------------------------

def test_predict_sin_qwen_configurada_no_rompe(session):
    import asyncio

    tenant, _ = _make_tenant_with_admin(session, "sin-qwen")
    result = asyncio.run(
        AIGatewayService.predict_product_success(
            session=session, tenant_id=tenant.id, name="Zapatillas", category="Calzado", price=Decimal("45000"),
        )
    )
    assert result["available"] is False
    assert "no está disponible" in result["message"]


def test_predict_con_qwen_devuelve_score_parseado(session, monkeypatch):
    import asyncio

    monkeypatch.setenv("QWEN_API_KEY", "fake-key-for-test")

    async def fake_chat(self, system_prompt, user_prompt):
        return json.dumps({
            "score": 82,
            "veredicto": "alto potencial",
            "razones": ["Buena categoria historica", "Precio competitivo"],
            "recomendacion": "Sumalo al catalogo destacado.",
        })

    monkeypatch.setattr(QwenClient, "chat", fake_chat)

    tenant, _ = _make_tenant_with_admin(session, "con-qwen")
    result = asyncio.run(
        AIGatewayService.predict_product_success(
            session=session, tenant_id=tenant.id, name="Zapatillas", category="Calzado", price=Decimal("45000"),
        )
    )
    assert result["available"] is True
    assert result["score"] == 82
    assert result["veredicto"] == "alto potencial"
    assert len(result["razones"]) == 2


def test_predict_respuesta_no_json_no_rompe(session, monkeypatch):
    import asyncio

    monkeypatch.setenv("QWEN_API_KEY", "fake-key-for-test")

    async def fake_chat(self, system_prompt, user_prompt):
        return "esto no es json"

    monkeypatch.setattr(QwenClient, "chat", fake_chat)

    tenant, _ = _make_tenant_with_admin(session, "respuesta-rota")
    result = asyncio.run(
        AIGatewayService.predict_product_success(
            session=session, tenant_id=tenant.id, name="Zapatillas", category="Calzado", price=Decimal("45000"),
        )
    )
    assert result["available"] is False


# ---------------------------------------------------------------------------
# Endpoint HTTP
# ---------------------------------------------------------------------------

def test_endpoint_requiere_login(client, session):
    resp = client.post(
        "/api/v1/ai/predict-product",
        json={"name": "Zapatillas", "category": "Calzado", "price": 45000},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307, 401)


def test_endpoint_logueado_sin_qwen(client, session):
    _make_tenant_with_admin(session, "endpoint-sin-qwen")
    _login(client, "admin")

    resp = client.post("/api/v1/ai/predict-product", json={"name": "Zapatillas", "category": "Calzado", "price": 45000})
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is False
