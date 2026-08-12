import os
os.environ["SECRET_KEY"] = "testsecretkey123"
os.environ["VIBECLOUD_FERNET_KEY"] = "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI="
os.environ["BASE_DOMAIN"] = "vibecloud.test"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from database.models import Settings, Tenant, TenantDomain, User
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


class FakeGoDaddyClient:
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
    from core.limiter import limiter, HAS_SLOWAPI
    if HAS_SLOWAPI:
        limiter.reset()
    yield


def _make_tenant_with_admin(session, subdomain, username, password="Contrasena123!", **flags):
    tenant = Tenant(name=subdomain, subdomain=subdomain, has_erp=True, has_ecommerce=True, has_landing=True)
    for k, v in flags.items():
        setattr(tenant, k, v)
    session.add(tenant)
    session.commit()
    session.refresh(tenant)

    settings_obj = Settings(tenant_id=tenant.id, company_name=subdomain)
    session.add(settings_obj)

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


def _login(client, username, password="Contrasena123!", host=None):
    headers = {"Host": host} if host else None
    return client.post("/login", data={"username": username, "password": password}, headers=headers, follow_redirects=False)


# ---------------------------------------------------------------------------
# Hub de entrada
# ---------------------------------------------------------------------------

def test_login_sin_modulo_muestra_el_hub(client, session):
    _make_tenant_with_admin(session, "acme", "admin")
    resp = _login(client, "admin")
    assert resp.status_code == 302

    home = client.get("/")
    assert home.status_code == 200
    assert "A qué módulo querés entrar" in home.text or "Hola," in home.text
    assert "Ingresar Datos" not in home.text  # no es el dashboard viejo


def test_hub_gatea_tiles_por_flags_reales(client, session):
    _make_tenant_with_admin(session, "solo-erp", "admin", has_erp=True, has_ecommerce=False, has_landing=False)
    _login(client, "admin")

    home = client.get("/")
    assert "ERP" in home.text
    assert "Buscar dominios" not in home.text  # sin ecommerce ni landing, no aplica


def test_entrar_a_erp_setea_nav_view_y_muestra_dashboard(client, session):
    _make_tenant_with_admin(session, "acme2", "admin")
    _login(client, "admin")

    resp = client.post("/panel/nav-view", data={"modules": ["erp"]})
    assert resp.status_code == 200

    home = client.get("/")
    assert "Actividad Reciente" in home.text  # dashboard.html real, no el hub


def test_registro_limpia_nav_view_viejo_de_otra_sesion(client, session):
    """Encontrado probando en vivo: si el navegador ya traia una cookie de
    sesion con nav_view seteado (de un login anterior en el mismo origen),
    /registro tiene que limpiarlo -- si no, el /  siguiente salta el hub
    y muestra el dashboard de ERP directo para una cuenta recien creada."""
    _make_tenant_with_admin(session, "previo", "yaexistia")
    _login(client, "yaexistia")
    client.post("/panel/nav-view", data={"modules": ["erp"]})
    home_before = client.get("/")
    assert "Actividad Reciente" in home_before.text  # confirma que nav_view quedo seteado

    resp = client.post(
        "/registro",
        data={
            "empresa": "Nueva Empresa",
            "subdominio": "nueva-empresa",
            "admin_username": "nuevoadmin",
            "admin_password": "Contrasena123!",
            "admin_email": "nuevoadmin@example.com",
            "has_erp": "true",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302

    home_after = client.get("/")
    assert "Actividad Reciente" not in home_after.text  # ahora tiene que ser el hub
    assert "Hola," in home_after.text


def test_onboarding_accesible_sin_nav_view(client, session):
    _make_tenant_with_admin(session, "acme3", "admin", has_ecommerce=True, has_landing=True)
    _login(client, "admin")

    resp = client.get("/panel/onboarding")
    assert resp.status_code == 200
    assert "Onboarding guiado" in resp.text


# ---------------------------------------------------------------------------
# Dominios self-service
# ---------------------------------------------------------------------------

def test_panel_dominios_solicitar_nunca_compra(client, session):
    tenant, _ = _make_tenant_with_admin(session, "acme4", "admin", has_ecommerce=True)
    _login(client, "admin")

    resp = client.post("/panel/dominios/solicitar", data={"domain": "acme4.com"})
    assert resp.status_code == 200

    row = session.exec(select(TenantDomain).where(TenantDomain.domain == "acme4.com")).first()
    assert row is not None
    assert row.status == "purchase_requested"
    assert row.tenant_id == tenant.id
    assert FakeGoDaddyClient.register_domain_calls == []


def test_panel_dominios_bloqueado_sin_ecommerce_ni_landing(client, session):
    _make_tenant_with_admin(session, "acme5", "admin", has_erp=True, has_ecommerce=False, has_landing=False)
    _login(client, "admin")

    resp = client.get("/panel/dominios")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Equipo + username por tenant
# ---------------------------------------------------------------------------

def test_dos_tenants_pueden_tener_cada_uno_su_admin(client, session):
    """El caso que motivó todo esto: dos negocios distintos, cada uno con
    un usuario 'admin', sin chocar entre si."""
    _make_tenant_with_admin(session, "negocio-uno", "admin")
    _make_tenant_with_admin(session, "negocio-dos", "admin")

    resp1 = _login(client, "admin", host="negocio-uno.vibecloud.test")
    assert resp1.status_code == 302
    resp2 = _login(client, "admin", host="negocio-dos.vibecloud.test")
    assert resp2.status_code == 302


def test_panel_equipo_crea_usuario_y_aisla_por_tenant(client, session):
    tenant_a, _ = _make_tenant_with_admin(session, "equipo-a", "admin")
    tenant_b, _ = _make_tenant_with_admin(session, "equipo-b", "admin")

    _login(client, "admin", host="equipo-a.vibecloud.test")
    resp = client.post(
        "/panel/equipo",
        data={"username": "cajera1", "password": "Contrasena123!", "role": "cashier"},
    )
    assert resp.status_code == 200
    assert "cajera1" in resp.text

    new_user = session.exec(select(User).where(User.username == "cajera1")).first()
    assert new_user.tenant_id == tenant_a.id

    # tenant B (logueado con SU PROPIO admin) no ve a la empleada de tenant A
    _login(client, "admin", host="equipo-b.vibecloud.test")
    page_b = client.get("/panel/equipo")
    assert page_b.status_code == 200
    assert "cajera1" not in page_b.text


def test_panel_equipo_username_duplicado_dentro_del_tenant(client, session):
    _make_tenant_with_admin(session, "equipo-c", "admin")
    _login(client, "admin", host="equipo-c.vibecloud.test")

    resp = client.post(
        "/panel/equipo",
        data={"username": "admin", "password": "Contrasena123!", "role": "cashier"},
        headers={"Host": "equipo-c.vibecloud.test"},
    )
    assert resp.status_code == 400
    assert "ya existe" in resp.text.lower()
