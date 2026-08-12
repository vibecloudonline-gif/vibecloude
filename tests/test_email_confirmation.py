import os
os.environ["SECRET_KEY"] = "testsecretkey123"
os.environ["VIBECLOUD_FERNET_KEY"] = "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI="

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from database.models import Tenant, User
from database.session import get_session
from main import app
import services.email_service as email_service


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
def ensure_smtp_unset(monkeypatch):
    # Por defecto, sin SMTP_HOST -- cada test que lo necesite lo prende
    # explicitamente con monkeypatch.setenv.
    monkeypatch.delenv("SMTP_HOST", raising=False)
    yield


BASE_FORM = {
    "empresa": "Mi Empresa SRL",
    "subdominio": "mi-empresa-mail",
    "admin_username": "admin1",
    "admin_password": "Contrasena123!",
    "admin_email": "admin1@example.com",
    "has_erp": "true",
}


def test_signup_sin_smtp_funciona_igual_que_antes(client, session):
    resp = client.post("/registro", data=BASE_FORM, follow_redirects=False)
    assert resp.status_code == 302  # auto-login de siempre, sin paso de confirmacion

    user = session.exec(select(User).where(User.username == "admin1")).first()
    assert user.is_active is True
    assert user.email == "admin1@example.com"


def test_signup_con_smtp_crea_usuario_inactivo_y_no_loguea(client, session, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.fake.test")
    sent = {}

    def fake_send(to_email, confirm_url, empresa):
        sent["to"] = to_email
        sent["url"] = confirm_url

    monkeypatch.setattr(email_service, "send_confirmation_email", fake_send)
    # routers/signup.py importo la funcion directamente (from ... import
    # send_confirmation_email) -- hay que parchear tambien esa referencia.
    import routers.signup as signup_router
    monkeypatch.setattr(signup_router, "send_confirmation_email", fake_send)

    resp = client.post("/registro", data=BASE_FORM, follow_redirects=False)
    assert resp.status_code == 200  # pantalla "revisa tu email", no redirect
    assert "revisá tu email" in resp.text.lower() or "revisa tu email" in resp.text.lower()

    user = session.exec(select(User).where(User.username == "admin1")).first()
    assert user.is_active is False
    assert sent["to"] == "admin1@example.com"
    assert "/confirmar-email?token=" in sent["url"]

    # No quedo logueado
    home = client.get("/", follow_redirects=False)
    assert home.status_code in (302, 307)
    assert home.headers.get("location") == "/login"


def test_login_rechazado_mientras_no_confirma(client, session, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.fake.test")
    import routers.signup as signup_router
    monkeypatch.setattr(signup_router, "send_confirmation_email", lambda *a, **k: None)

    client.post("/registro", data=BASE_FORM, follow_redirects=False)
    resp = client.post("/login", data={"username": "admin1", "password": "Contrasena123!"})
    assert "Credenciales inválidas" in resp.text


def test_confirmar_email_activa_y_loguea(client, session, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.fake.test")
    captured = {}

    def fake_send(to_email, confirm_url, empresa):
        captured["url"] = confirm_url

    import routers.signup as signup_router
    monkeypatch.setattr(signup_router, "send_confirmation_email", fake_send)

    client.post("/registro", data=BASE_FORM, follow_redirects=False)
    token = captured["url"].split("token=")[1]

    resp = client.get(f"/confirmar-email?token={token}", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/"

    user = session.exec(select(User).where(User.username == "admin1")).first()
    assert user.is_active is True

    home = client.get("/")
    assert home.status_code == 200  # ya logueado, ve el hub


def test_confirmar_email_token_invalido(client, session):
    resp = client.get("/confirmar-email?token=basura-no-es-un-token-valido")
    assert resp.status_code == 400
    assert "ya no es válido" in resp.text.lower() or "no es valido" in resp.text.lower()


def test_confirmar_email_token_vencido(client, session, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.fake.test")
    import routers.signup as signup_router
    monkeypatch.setattr(signup_router, "send_confirmation_email", lambda *a, **k: None)
    client.post("/registro", data=BASE_FORM, follow_redirects=False)

    user = session.exec(select(User).where(User.username == "admin1")).first()
    token = email_service.generate_confirm_token(user.id)

    # max_age negativo == "ya vencio" sin tener que esperar de verdad.
    result = email_service.verify_confirm_token(token, max_age=-1)
    assert result is None


def test_email_invalido_rechazado(client, session):
    bad_form = {**BASE_FORM, "admin_email": "no-es-un-email"}
    resp = client.post("/registro", data=bad_form, follow_redirects=False)
    assert resp.status_code == 400
    assert "email" in resp.text.lower()
