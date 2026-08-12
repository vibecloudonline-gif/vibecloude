import os
os.environ["SECRET_KEY"] = "testsecretkey123"
os.environ["VIBECLOUD_FERNET_KEY"] = "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI="

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from database.models import Settings, SupportTicket, Tenant, User
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


def _make_tenant_with_admin(session, subdomain, username="admin", password="Contrasena123!", **flags):
    tenant = Tenant(name=subdomain, subdomain=subdomain, has_erp=True)
    for k, v in flags.items():
        setattr(tenant, k, v)
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


def _make_superadmin(session, tenant_id, username="root", password="Contrasena123!"):
    user = User(
        username=username,
        password_hash=AuthService.get_password_hash(password),
        role="superadmin",
        tenant_id=tenant_id,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _login(client, username, password="Contrasena123!"):
    return client.post("/login", data={"username": username, "password": password}, follow_redirects=False)


# ---------------------------------------------------------------------------
# Centro de ayuda del tenant
# ---------------------------------------------------------------------------

def test_ayuda_requiere_login(client, session):
    resp = client.get("/panel/ayuda", follow_redirects=False)
    assert resp.status_code in (302, 307)


def test_ayuda_muestra_faq_gateada_por_flags(client, session):
    _make_tenant_with_admin(session, "solo-erp", has_erp=True, has_ecommerce=False, has_landing=False)
    _login(client, "admin")

    resp = client.get("/panel/ayuda")
    assert resp.status_code == 200
    assert "Predicción de viabilidad" in resp.text
    assert "AlexIO" not in resp.text  # sin ecommerce/landing, no aplica


def test_crear_ticket_funciona(client, session):
    tenant, _ = _make_tenant_with_admin(session, "con-ticket")
    _login(client, "admin")

    resp = client.post("/panel/ayuda/ticket", data={"subject": "No puedo cargar stock", "message": "Me tira error al guardar."})
    assert resp.status_code == 200
    assert "enviada" in resp.text.lower()

    ticket = session.exec(select(SupportTicket).where(SupportTicket.tenant_id == tenant.id)).first()
    assert ticket is not None
    assert ticket.subject == "No puedo cargar stock"
    assert ticket.status == "open"


def test_crear_ticket_vacio_rechazado(client, session):
    _make_tenant_with_admin(session, "ticket-vacio")
    _login(client, "admin")

    resp = client.post("/panel/ayuda/ticket", data={"subject": "  ", "message": "  "})
    assert resp.status_code == 200
    assert "Completá" in resp.text

    tickets = session.exec(select(SupportTicket)).all()
    assert tickets == []


def test_tenant_no_ve_tickets_de_otro_tenant(client, session):
    # Usernames distintos a proposito -- sin BASE_DOMAIN en este test, el
    # login cae al fallback global (ambiguo si dos tenants comparten
    # username, ver routers/auth.py), asi que se evita esa ambiguedad para
    # que el test valide aislamiento de tickets, no el fallback de login.
    tenant_a, _ = _make_tenant_with_admin(session, "tickets-a", username="admin-a")
    tenant_b, _ = _make_tenant_with_admin(session, "tickets-b", username="admin-b")

    ticket_a = SupportTicket(tenant_id=tenant_a.id, subject="De A", message="msg a")
    ticket_b = SupportTicket(tenant_id=tenant_b.id, subject="De B", message="msg b")
    session.add(ticket_a)
    session.add(ticket_b)
    session.commit()

    _login(client, "admin-a")
    resp = client.get("/panel/ayuda")
    assert resp.status_code == 200
    assert "De A" in resp.text
    assert "De B" not in resp.text


# ---------------------------------------------------------------------------
# Bandeja de SuperAdmin
# ---------------------------------------------------------------------------

def test_tickets_superadmin_requiere_rol(client, session):
    _make_tenant_with_admin(session, "no-superadmin")
    _login(client, "admin")

    resp = client.get("/tickets", follow_redirects=False)
    assert resp.status_code == 403


def test_tickets_superadmin_ve_todos_y_responde(client, session):
    tenant_a, _ = _make_tenant_with_admin(session, "sa-tenant-a")
    tenant_b, _ = _make_tenant_with_admin(session, "sa-tenant-b")
    _make_superadmin(session, tenant_id=tenant_a.id)

    ticket = SupportTicket(tenant_id=tenant_b.id, subject="Duda de dominio", message="No me anda la verificacion.")
    session.add(ticket)
    session.commit()
    session.refresh(ticket)

    _login(client, "root")
    resp = client.get("/tickets")
    assert resp.status_code == 200
    assert "Duda de dominio" in resp.text
    assert "sa-tenant-b" in resp.text

    resp2 = client.post(f"/tickets/{ticket.id}/responder", data={"response": "Ya te lo confirmamos."}, follow_redirects=False)
    assert resp2.status_code == 302

    session.refresh(ticket)
    assert ticket.status == "answered"
    assert ticket.response == "Ya te lo confirmamos."
    assert ticket.responded_at is not None
