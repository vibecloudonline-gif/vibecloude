import os
os.environ["SECRET_KEY"] = "testsecretkey123"
os.environ["VIBECLOUD_FERNET_KEY"] = "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI="

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from main import app
from database.session import get_session
from database.models import User, Tenant, UIConfig
from services.jwt_service import create_access_token
from sqlalchemy.pool import StaticPool

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

def test_get_ui_config_requires_auth(client):
    response = client.get("/api/v1/ui-config/pos")
    assert response.status_code == 422  # Missing header

def test_get_ui_config_returns_defaults(client, session):
    tenant = Tenant(name="Tenant 1", subdomain="t1")
    session.add(tenant)
    session.commit()

    user = User(username="u1", password_hash="hash", role="vendedor", tenant_id=tenant.id)
    session.add(user)
    session.commit()

    token = create_access_token(user.id, tenant.id, user.role)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/v1/ui-config/pos", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["page_name"] == "pos"
    assert "modules" in data["layout"]
    assert "primary_color" in data["theme"]

def test_get_ui_config_existing(client, session):
    tenant = Tenant(name="Tenant 1", subdomain="t1")
    session.add(tenant)
    session.commit()

    user = User(username="u1", password_hash="hash", role="vendedor", tenant_id=tenant.id)
    session.add(user)
    session.commit()

    config = UIConfig(
        tenant_id=tenant.id,
        page_name="pos",
        layout_json='{"custom_layout": true}',
        theme_json='{"custom_theme": true}'
    )
    session.add(config)
    session.commit()

    token = create_access_token(user.id, tenant.id, user.role)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/v1/ui-config/pos", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["layout"] == {"custom_layout": True}
    assert data["theme"] == {"custom_theme": True}

def test_put_ui_config_role_check(client, session):
    tenant = Tenant(name="Tenant 1", subdomain="t1")
    session.add(tenant)
    session.commit()

    # Vendedor: should get 403
    user_vendedor = User(username="vendedor", password_hash="hash", role="vendedor", tenant_id=tenant.id)
    session.add(user_vendedor)
    session.commit()

    # Admin: should succeed
    user_admin = User(username="admin", password_hash="hash", role="admin", tenant_id=tenant.id)
    session.add(user_admin)
    session.commit()

    layout_data = {"modules": ["test"]}
    theme_data = {"primary_color": "#ff0000"}

    # Test as seller
    token_vendedor = create_access_token(user_vendedor.id, tenant.id, user_vendedor.role)
    headers_vendedor = {"Authorization": f"Bearer {token_vendedor}"}
    response_v = client.put(
        "/api/v1/ui-config/pos",
        json={"layout": layout_data, "theme": theme_data},
        headers=headers_vendedor
    )
    assert response_v.status_code == 403

    # Test as admin
    token_admin = create_access_token(user_admin.id, tenant.id, user_admin.role)
    headers_admin = {"Authorization": f"Bearer {token_admin}"}
    response_a = client.put(
        "/api/v1/ui-config/pos",
        json={"layout": layout_data, "theme": theme_data},
        headers=headers_admin
    )
    assert response_a.status_code == 200
    data = response_a.json()
    assert data["layout"] == layout_data
    assert data["theme"] == theme_data

    # Verify database
    db_config = session.exec(select(UIConfig).where(UIConfig.tenant_id == tenant.id, UIConfig.page_name == "pos")).first()
    assert db_config is not None
    import json
    assert json.loads(db_config.layout_json) == layout_data

def test_cross_tenant_ui_config_isolation(client, session):
    tenant1 = Tenant(name="T1", subdomain="t1")
    tenant2 = Tenant(name="T2", subdomain="t2")
    session.add(tenant1)
    session.add(tenant2)
    session.commit()

    user1 = User(username="admin1", password_hash="hash", role="admin", tenant_id=tenant1.id)
    user2 = User(username="admin2", password_hash="hash", role="admin", tenant_id=tenant2.id)
    session.add(user1)
    session.add(user2)
    session.commit()

    # Admin 1 writes a config
    layout1 = {"t": 1}
    theme1 = {"c": "blue"}
    token1 = create_access_token(user1.id, tenant1.id, user1.role)
    headers1 = {"Authorization": f"Bearer {token1}"}

    response_put = client.put(
        "/api/v1/ui-config/dashboard",
        json={"layout": layout1, "theme": theme1},
        headers=headers1
    )
    assert response_put.status_code == 200

    # Admin 2 gets config for dashboard. Should get default config, NOT Admin 1's config.
    token2 = create_access_token(user2.id, tenant2.id, user2.role)
    headers2 = {"Authorization": f"Bearer {token2}"}

    response_get = client.get("/api/v1/ui-config/dashboard", headers=headers2)
    assert response_get.status_code == 200
    data = response_get.json()
    assert data["layout"] != layout1
    assert "modules" in data["layout"]  # Default layout
