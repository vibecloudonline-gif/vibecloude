import os
os.environ["SECRET_KEY"] = "testsecretkey123"
os.environ["VIBECLOUD_FERNET_KEY"] = "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI="

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from database.models import Tenant, TenantDomain, Settings, User
from database.session import get_session
from main import app
from services.auth_service import AuthService
import routers.admin as admin_router
import routers.signup as signup_router


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


class FakeGoDaddyClient:
    """Stand-in para GoDaddyClient -- nunca pega a la red real. Registra si
    alguien llamó a register_domain (una compra real) para poder asserterlo."""
    register_domain_calls = []
    check_availability_result = True

    def __init__(self, *args, **kwargs):
        pass

    async def check_availability(self, domain):
        return FakeGoDaddyClient.check_availability_result

    async def register_domain(self, domain, years=1, contact=None):
        FakeGoDaddyClient.register_domain_calls.append(domain)
        return {"status": "purchased", "domain": domain}


@pytest.fixture(autouse=True)
def patch_godaddy(monkeypatch):
    FakeGoDaddyClient.register_domain_calls = []
    FakeGoDaddyClient.check_availability_result = True
    import services.domain_registrar_service as drs
    monkeypatch.setattr(drs, "GoDaddyClient", FakeGoDaddyClient)
    yield


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    # El limiter en memoria de slowapi persiste entre tests dentro del mismo
    # proceso (misma IP simulada de TestClient) -- sin resetear, tests
    # posteriores del mismo endpoint reciben 429 en vez del status esperado.
    from core.limiter import limiter, HAS_SLOWAPI
    if HAS_SLOWAPI:
        limiter.reset()
    yield


BASE_FORM = {
    "empresa": "Mi Empresa SRL",
    "admin_username": "admin1",
    "admin_password": "Contrasena123!",
    "admin_email": "admin1@example.com",
    "admin_full_name": "Alex",
}


def test_signup_solo_erp(client, session):
    resp = client.post(
        "/registro",
        data={**BASE_FORM, "subdominio": "solo-erp", "has_erp": "true"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    tenant = session.exec(select(Tenant).where(Tenant.subdomain == "solo-erp")).first()
    assert tenant is not None
    assert tenant.has_erp is True
    assert tenant.has_ecommerce is False
    assert tenant.has_landing is False
    assert tenant.has_alexio is False
    assert FakeGoDaddyClient.register_domain_calls == []


def test_signup_web_landing_only(client, session):
    resp = client.post(
        "/registro",
        data={**BASE_FORM, "subdominio": "solo-landing", "has_landing": "true"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    tenant = session.exec(select(Tenant).where(Tenant.subdomain == "solo-landing")).first()
    assert tenant.has_landing is True
    assert tenant.has_erp is False
    assert tenant.has_ecommerce is False


def test_signup_web_ecommerce_dominio_y_conector_nunca_compra(client, session):
    """El paso de dominio nunca debe disparar una compra real, aunque el
    usuario pida comprarlo -- solo crea una solicitud pendiente."""
    resp = client.post(
        "/registro",
        data={
            **BASE_FORM,
            "subdominio": "tienda-full",
            "has_erp": "true",
            "has_ecommerce": "true",
            "domain_choice": "comprar",
            "desired_domain": "tienda-full.com",
            "ecommerce_connected_to_erp": "true",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302

    tenant = session.exec(select(Tenant).where(Tenant.subdomain == "tienda-full")).first()
    assert tenant.has_erp is True
    assert tenant.has_ecommerce is True

    settings_obj = session.exec(select(Settings).where(Settings.tenant_id == tenant.id)).first()
    assert settings_obj.ecommerce_connected_to_erp is True

    domain_row = session.exec(select(TenantDomain).where(TenantDomain.domain == "tienda-full.com")).first()
    assert domain_row is not None
    assert domain_row.status == "purchase_requested"
    assert domain_row.tenant_id == tenant.id

    # La garantia de seguridad: jamas se llamo a la compra real de GoDaddy.
    assert FakeGoDaddyClient.register_domain_calls == []


def test_signup_conector_ignorado_si_no_tiene_ambos(client, session):
    resp = client.post(
        "/registro",
        data={
            **BASE_FORM,
            "subdominio": "solo-ecommerce",
            "has_ecommerce": "true",
            "ecommerce_connected_to_erp": "true",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    tenant = session.exec(select(Tenant).where(Tenant.subdomain == "solo-ecommerce")).first()
    settings_obj = session.exec(select(Settings).where(Settings.tenant_id == tenant.id)).first()
    # Sin ERP no aplica el conector, aunque el form lo mande en true.
    assert settings_obj.ecommerce_connected_to_erp is False


def test_signup_sin_productos_rechazado(client, session):
    resp = client.post(
        "/registro",
        data={**BASE_FORM, "subdominio": "sin-producto"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert session.exec(select(Tenant).where(Tenant.subdomain == "sin-producto")).first() is None


def test_signup_subdominio_duplicado_integrity_error_manejado(client, session):
    existing = Tenant(name="Ya existe", subdomain="ocupado", has_erp=True)
    session.add(existing)
    session.commit()

    # Se salta el pre-chequeo simulando una carrera: el subdominio pasa la
    # validacion de formato pero ya existe en el momento del commit.
    resp = client.post(
        "/registro",
        data={**BASE_FORM, "subdominio": "ocupado", "has_erp": "true"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "en uso" in resp.text


def test_dominio_disponible_endpoint(client, session):
    FakeGoDaddyClient.check_availability_result = True
    resp = client.get("/api/registro/dominio-disponible?dominio=libre-total.com")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is True

    FakeGoDaddyClient.check_availability_result = False
    resp2 = client.get("/api/registro/dominio-disponible?dominio=tomado.com")
    assert resp2.json()["available"] is False


def _make_superadmin(session):
    tenant = Tenant(name="Platform", subdomain="platform-admin")
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    user = User(
        username="root",
        password_hash=AuthService.get_password_hash("RootPass123!"),
        role="superadmin",
        tenant_id=tenant.id,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_superadmin_confirma_compra_de_solicitud_pendiente(client, session):
    tenant = Tenant(name="Cliente Web", subdomain="cliente-web", has_erp=False, has_ecommerce=True)
    session.add(tenant)
    session.commit()
    session.refresh(tenant)

    pending = TenantDomain(
        tenant_id=tenant.id,
        domain="clienteweb.com",
        verification_token="placeholder",
        status="purchase_requested",
    )
    session.add(pending)
    session.commit()

    _make_superadmin(session)
    login_resp = client.post(
        "/login",
        data={"username": "root", "password": "RootPass123!"},
        follow_redirects=False,
    )
    assert login_resp.status_code == 302

    resp = client.post(
        f"/api/tenants/{tenant.id}/domains/comprar",
        data={"domain": "clienteweb.com", "years": "1"},
    )
    assert resp.status_code == 200
    assert FakeGoDaddyClient.register_domain_calls == ["clienteweb.com"]

    rows = session.exec(select(TenantDomain).where(TenantDomain.domain == "clienteweb.com")).all()
    assert len(rows) == 1  # se actualizo la fila existente, no se duplico
    assert rows[0].status == "verified"
