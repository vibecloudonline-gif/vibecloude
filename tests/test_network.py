"""Tests for the VibeNet network module."""
import os
os.environ.setdefault("SECRET_KEY", "testsecretkey123")
os.environ.setdefault("VIBECLOUD_API_KEY", "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI=")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from database.models import (
    BusinessCategory, BusinessProfile, Connection, Conversation,
    NetMessage, BusinessReview, FeedPost, Tenant, User, Settings,
)
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


def _make_tenant(session, name="T1", subdomain="t1"):
    tenant = Tenant(name=name, subdomain=subdomain, has_landing=True, has_ecommerce=True, nivel=3)
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    user = User(
        username=f"admin_{subdomain}", role="admin", tenant_id=tenant.id,
        password_hash=AuthService.get_password_hash("TestPass123!"),
    )
    session.add(user)
    settings = Settings(tenant_id=tenant.id, company_name=name)
    session.add(settings)
    session.commit()
    session.refresh(user)
    return tenant, user


def _login(client, username="admin_t1"):
    client.post("/login", data={"username": username, "password": "TestPass123!"}, follow_redirects=False)


# --- Public pages ---

def test_feed_page(client, session):
    resp = client.get("/red")
    assert resp.status_code == 200
    assert "VibeNet" in resp.text


def test_directorio_page(client, session):
    resp = client.get("/red/directorio")
    assert resp.status_code == 200
    assert "Directorio" in resp.text


def test_directorio_search(client, session):
    t, u = _make_tenant(session)
    profile = BusinessProfile(tenant_id=t.id, display_name="Zapatos Online", city="Buenos Aires")
    session.add(profile)
    session.commit()
    resp = client.get("/red/directorio?q=Zapatos")
    assert resp.status_code == 200
    assert "Zapatos Online" in resp.text


def test_directorio_filter_city(client, session):
    t, u = _make_tenant(session)
    profile = BusinessProfile(tenant_id=t.id, display_name="Local BA", city="Buenos Aires")
    session.add(profile)
    session.commit()
    resp = client.get("/red/directorio?ciudad=Buenos")
    assert resp.status_code == 200
    assert "Local BA" in resp.text


def test_profile_public(client, session):
    t, u = _make_tenant(session)
    profile = BusinessProfile(tenant_id=t.id, display_name="MiNegocio")
    session.add(profile)
    session.commit()
    session.refresh(profile)
    resp = client.get(f"/red/perfil/{profile.id}")
    assert resp.status_code == 200
    assert "MiNegocio" in resp.text


def test_profile_404(client, session):
    resp = client.get("/red/perfil/99999")
    assert resp.status_code == 404


# --- Panel ---

def test_panel_red_dashboard(client, session):
    _make_tenant(session)
    _login(client)
    resp = client.get("/panel/red")
    assert resp.status_code == 200
    assert "VibeNet" in resp.text


def test_create_profile(client, session):
    t, u = _make_tenant(session)
    _login(client)
    resp = client.post("/panel/red/perfil", data={
        "display_name": "Mi Empresa",
        "tagline": "Lo mejor",
        "description": "",
        "category_id": "",
        "city": "Córdoba",
        "country": "AR",
        "website_url": "",
        "social_instagram": "@miempresa",
        "social_linkedin": "",
        "social_twitter": "",
    }, follow_redirects=False)
    assert resp.status_code == 302
    profile = session.exec(select(BusinessProfile).where(BusinessProfile.tenant_id == t.id)).first()
    assert profile is not None
    assert profile.display_name == "Mi Empresa"
    assert profile.city == "Córdoba"


# --- Connections ---

def test_connection_flow(session):
    t1 = Tenant(name="A", subdomain="a")
    t2 = Tenant(name="B", subdomain="b")
    session.add_all([t1, t2])
    session.commit()
    session.refresh(t1)
    session.refresh(t2)
    conn = Connection(from_tenant_id=t1.id, to_tenant_id=t2.id, connection_type="partner")
    session.add(conn)
    session.commit()
    session.refresh(conn)
    assert conn.status == "pending"
    conn.status = "accepted"
    from datetime import datetime, timezone
    conn.accepted_at = datetime.now(timezone.utc)
    session.add(conn)
    session.commit()
    assert conn.status == "accepted"


def test_self_connection_blocked(client, session):
    t, u = _make_tenant(session)
    _login(client)
    resp = client.post(f"/panel/red/conectar/{t.id}", data={"connection_type": "partner", "message": ""})
    assert resp.status_code == 400


# --- Messaging ---

def test_messaging(session):
    t1 = Tenant(name="A", subdomain="a")
    t2 = Tenant(name="B", subdomain="b")
    session.add_all([t1, t2])
    session.commit()
    session.refresh(t1)
    session.refresh(t2)
    convo = Conversation(tenant_a_id=t1.id, tenant_b_id=t2.id)
    session.add(convo)
    session.commit()
    session.refresh(convo)
    msg = NetMessage(conversation_id=convo.id, sender_tenant_id=t1.id, body="Hola!")
    session.add(msg)
    session.commit()
    session.refresh(msg)
    assert msg.body == "Hola!"
    assert msg.read_at is None


# --- Reviews ---

def test_review_model(session):
    t1 = Tenant(name="A", subdomain="a")
    t2 = Tenant(name="B", subdomain="b")
    session.add_all([t1, t2])
    session.commit()
    session.refresh(t1)
    session.refresh(t2)
    profile = BusinessProfile(tenant_id=t1.id, display_name="Negocio A")
    session.add(profile)
    session.commit()
    session.refresh(profile)
    review = BusinessReview(
        profile_id=profile.id, reviewer_tenant_id=t2.id,
        rating=5, title="Excelente", comment="Muy buen servicio",
    )
    session.add(review)
    session.commit()
    session.refresh(review)
    assert review.rating == 5
    assert review.is_verified_connection is False


def test_cannot_review_self(client, session):
    t, u = _make_tenant(session)
    _login(client)
    profile = BusinessProfile(tenant_id=t.id, display_name="Self")
    session.add(profile)
    session.commit()
    session.refresh(profile)
    resp = client.post(f"/panel/red/review/{profile.id}", data={
        "rating": "5", "title": "Yo", "comment": "Me auto-reseño",
    })
    assert resp.status_code == 400


# --- Feed ---

def test_feed_post(client, session):
    t, u = _make_tenant(session)
    _login(client)
    resp = client.post("/panel/red/publicar", data={
        "title": "Nuevo producto!",
        "body": "Lanzamos algo nuevo",
        "post_type": "product_launch",
    }, follow_redirects=False)
    assert resp.status_code == 302
    post = session.exec(select(FeedPost).where(FeedPost.tenant_id == t.id)).first()
    assert post is not None
    assert post.title == "Nuevo producto!"
    assert post.post_type == "product_launch"


# --- Categories ---

def test_business_categories(session):
    cat = BusinessCategory(name="Tech", slug="tech", icon="💻")
    session.add(cat)
    session.commit()
    session.refresh(cat)
    sub = BusinessCategory(name="Software", slug="software", parent_id=cat.id)
    session.add(sub)
    session.commit()
    session.refresh(sub)
    assert sub.parent_id == cat.id
