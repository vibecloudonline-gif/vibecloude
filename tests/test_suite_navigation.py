"""Tests for Suite Navigation Architecture (Block 6)
- Absence of raw checkboxes in the sidebar
- Contextual suite isolation (/panel/research does not show retail ERP operational links)
- Shared links (/products, /sales, /clients, /catalog-import, /reports) available in Web & Storefront
- Alex Agent link gated specifically on tenant_flags.alexio
- Coexistence with POST /panel/nav-view
"""
import pytest
from bs4 import BeautifulSoup
from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from main import app
from database.session import get_session
from database.models import Tenant, User, Settings
from web.dependencies import require_auth


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def client(test_db):
    app.dependency_overrides[get_session] = lambda: test_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_no_checkboxes_in_suite_switcher(client, test_db):
    """Verifica que no existan checkboxes crudos (type='checkbox') en la navegacion."""
    tenant = Tenant(name="T1", subdomain="t1", has_erp=True, has_ecommerce=True, has_landing=True)
    test_db.add(tenant)
    test_db.commit()
    test_db.refresh(tenant)

    user = User(tenant_id=tenant.id, username="admin_t1", password_hash="hash", role="admin", is_active=True)
    test_db.add(user)
    settings = Settings(tenant_id=tenant.id, company_name="T1 Co")
    test_db.add(settings)
    test_db.commit()

    app.dependency_overrides[require_auth] = lambda: user

    try:
        resp = client.get("/pos", headers={"x-tenant-subdomain": "t1"})
        assert resp.status_code == 200
        html = resp.text

        soup = BeautifulSoup(html, "html.parser")
        sidebar = soup.find("aside", class_="sidebar")
        assert sidebar is not None
        checkboxes = sidebar.find_all("input", {"type": "checkbox"})
        assert len(checkboxes) == 0, f"Se encontraron checkboxes crudos en el sidebar: {checkboxes}"
        
        switcher_btn = sidebar.find(id="suiteSwitcherBtn")
        assert switcher_btn is not None
        dropdown = sidebar.find(id="suiteDropdown")
        assert dropdown is not None
    finally:
        app.dependency_overrides.pop(require_auth, None)


def test_erp_isolation_on_research_page(client, test_db):
    """Verifica que en /panel/research NO se rendericen en el menu operativo los enlaces del ERP (POS, Caja, Proveedores, WMS)."""
    tenant = Tenant(name="T1", subdomain="t1", has_erp=True, has_ecommerce=True, has_landing=True, has_alexio=True)
    test_db.add(tenant)
    test_db.commit()
    test_db.refresh(tenant)

    user = User(tenant_id=tenant.id, username="admin_t1", password_hash="hash", role="admin", is_active=True)
    test_db.add(user)
    settings = Settings(tenant_id=tenant.id, company_name="T1 Co")
    test_db.add(settings)
    test_db.commit()

    def mock_auth(request: Request):
        request.session["tenant_flags"] = {
            "erp": tenant.has_erp,
            "ecommerce": tenant.has_ecommerce,
            "landing": tenant.has_landing,
            "alexio": tenant.has_alexio,
        }
        return user

    from fastapi import Request
    app.dependency_overrides[require_auth] = mock_auth

    try:
        resp = client.get("/panel/research", headers={"x-tenant-subdomain": "t1"})
        assert resp.status_code == 200
        html = resp.text

        soup = BeautifulSoup(html, "html.parser")
        nav = soup.find("nav", class_="sidebar-links")
        assert nav is not None
        nav_links = [a.get("href") for a in nav.find_all("a", href=True)]

        # En Alex IO Studio el menu no debe tener herramientas operativas exclusivas de ERP
        assert "/pos" not in nav_links
        assert "/cash" not in nav_links
        assert "/suppliers" not in nav_links
        assert "/wms/depositos" not in nav_links
        assert "/picking" not in nav_links

        # Pero si debe tener las de investigación y lanzamiento
        assert "/panel/research" in nav_links
        assert "/panel/landing" in nav_links
        assert "/panel/alex-agent" in nav_links
    finally:
        app.dependency_overrides.pop(require_auth, None)


def test_shared_links_visible_in_web_suite(client, test_db):
    """Verifica que un tenant con has_ecommerce=True y has_erp=False en suite Web vea los 5 links compartidos en su navegacion."""
    tenant = Tenant(name="T2", subdomain="t2", has_erp=False, has_ecommerce=True, has_landing=True, has_alexio=False)
    test_db.add(tenant)
    test_db.commit()
    test_db.refresh(tenant)

    user = User(tenant_id=tenant.id, username="web_user", password_hash="hash", role="admin", is_active=True)
    test_db.add(user)
    settings = Settings(tenant_id=tenant.id, company_name="Web Store")
    test_db.add(settings)
    test_db.commit()

    app.dependency_overrides[require_auth] = lambda: user

    try:
        resp = client.get("/panel/landing", headers={"x-tenant-subdomain": "t2"})
        assert resp.status_code == 200
        html = resp.text

        soup = BeautifulSoup(html, "html.parser")
        nav = soup.find("nav", class_="sidebar-links")
        assert nav is not None
        nav_links = [a.get("href") for a in nav.find_all("a", href=True)]

        # 5 links compartidos deben estar presentes en nav para ecommerce
        assert "/products" in nav_links, "Stock debe estar en suite web para ecommerce"
        assert "/sales" in nav_links, "Ventas debe estar en suite web para ecommerce"
        assert "/clients" in nav_links, "Clientes debe estar en suite web para ecommerce"
        assert "/catalog-import" in nav_links, "Importar catalogo debe estar en suite web para ecommerce"
        assert "/reports" in nav_links, "Reportes debe estar en suite web para ecommerce"

        # Y NO debe tener las herramientas exclusivas de ERP
        assert "/pos" not in nav_links
        assert "/cash" not in nav_links
        assert "/wms/depositos" not in nav_links
    finally:
        app.dependency_overrides.pop(require_auth, None)


def test_alex_agent_link_gated_by_alexio_flag(client, test_db):
    """Verifica que /panel/alex-agent solo aparezca si has_alexio es True."""
    tenant_no_alex = Tenant(name="T3", subdomain="t3", has_erp=True, has_ecommerce=False, has_landing=True, has_alexio=False)
    test_db.add(tenant_no_alex)
    test_db.commit()
    test_db.refresh(tenant_no_alex)

    user = User(tenant_id=tenant_no_alex.id, username="no_alex_user", password_hash="hash", role="admin", is_active=True)
    test_db.add(user)
    settings = Settings(tenant_id=tenant_no_alex.id, company_name="No Alex")
    test_db.add(settings)
    test_db.commit()

    app.dependency_overrides[require_auth] = lambda: user

    try:
        resp = client.get("/panel/research", headers={"x-tenant-subdomain": "t3"})
        assert resp.status_code == 200
        soup = BeautifulSoup(resp.text, "html.parser")
        nav = soup.find("nav", class_="sidebar-links")
        nav_links = [a.get("href") for a in nav.find_all("a", href=True)]

        assert "/panel/alex-agent" not in nav_links, "/panel/alex-agent no debe aparecer sin flag alexio"
    finally:
        app.dependency_overrides.pop(require_auth, None)


def test_nav_view_post_coexistence(client, test_db):
    """Verifica que POST /panel/nav-view persista correctamente en session y conviva con la arquitectura de suite."""
    tenant = Tenant(name="T4", subdomain="t4", has_erp=True, has_ecommerce=True, has_landing=True, has_alexio=True)
    test_db.add(tenant)
    test_db.commit()
    test_db.refresh(tenant)

    user = User(tenant_id=tenant.id, username="admin_t4", password_hash="hash", role="admin", is_active=True)
    test_db.add(user)
    settings = Settings(tenant_id=tenant.id, company_name="T4 Co")
    test_db.add(settings)
    test_db.commit()

    def mock_auth(request: Request):
        request.session["tenant_flags"] = {
            "erp": tenant.has_erp,
            "ecommerce": tenant.has_ecommerce,
            "landing": tenant.has_landing,
            "alexio": tenant.has_alexio,
        }
        return user

    from fastapi import Request
    app.dependency_overrides[require_auth] = mock_auth

    try:
        resp = client.post("/panel/nav-view", data={"modules": ["erp"]}, headers={"x-tenant-subdomain": "t4"})
        assert resp.status_code == 200
        assert resp.json() == {"status": "success", "view": ["erp"]}

        # Post alexio
        resp_alex = client.post("/panel/nav-view", data={"modules": ["alexio"]}, headers={"x-tenant-subdomain": "t4"})
        assert resp_alex.status_code == 200
        assert resp_alex.json() == {"status": "success", "view": ["alexio"]}
    finally:
        app.dependency_overrides.pop(require_auth, None)


def test_research_page_renders_scripts_and_creates_project(client, test_db):
    """Verifica que /panel/research renderice los bloques extra_css y extra_js, y que el flujo de creacion funcione."""
    tenant = Tenant(name="T5", subdomain="t5", has_erp=True, has_ecommerce=True, has_landing=True, has_alexio=True)
    test_db.add(tenant)
    test_db.commit()
    test_db.refresh(tenant)

    user = User(tenant_id=tenant.id, username="admin_t5", password_hash="hash", role="admin", is_active=True)
    test_db.add(user)
    settings = Settings(tenant_id=tenant.id, company_name="T5 Co")
    test_db.add(settings)
    test_db.commit()

    def mock_auth(request: Request):
        request.session["tenant_flags"] = {
            "erp": tenant.has_erp,
            "ecommerce": tenant.has_ecommerce,
            "landing": tenant.has_landing,
            "alexio": tenant.has_alexio,
        }
        return user

    from fastapi import Request
    app.dependency_overrides[require_auth] = mock_auth

    try:
        # 1. GET /panel/research debe contener los scripts y estilos de extra_js y extra_css
        resp_get = client.get("/panel/research", headers={"x-tenant-subdomain": "t5"})
        assert resp_get.status_code == 200
        html = resp_get.text
        assert "btn-new" in html
        assert "create-form" in html
        assert "new-form-wrap" in html
        assert ".new-form" in html  # extra_css cargado
        assert "addEventListener('submit'" in html  # extra_js cargado

        # 2. POST /panel/research/nuevo crea el proyecto exitosamente
        resp_create = client.post(
            "/panel/research/nuevo",
            data={
                "project_type": "physical_product",
                "query_description": "Smartwatch con pulsometro deportivo",
                "reference_url": "https://example.com/watch",
                "factory_price": "25.50",
            },
            headers={"x-tenant-subdomain": "t5", "Accept": "application/json"},
        )
        assert resp_create.status_code == 200
        data = resp_create.json()
        assert data["status"] == "success"
        project_id = data["project_id"]

        # 3. GET /panel/research/{project_id} muestra la vista de detalle
        resp_detail = client.get(f"/panel/research/{project_id}", headers={"x-tenant-subdomain": "t5"})
        assert resp_detail.status_code == 200
        assert "Smartwatch con pulsometro deportivo" in resp_detail.text
        assert "Iniciar busqueda" in resp_detail.text

        # 4. POST /panel/research/{project_id}/buscar ejecuta la busqueda de mercado
        resp_search = client.post(
            f"/panel/research/{project_id}/buscar",
            headers={"x-tenant-subdomain": "t5"},
        )
        assert resp_search.status_code == 200
        search_data = resp_search.json()
        assert search_data["status"] == "success"
        assert search_data["listings_count"] > 0
    finally:
        app.dependency_overrides.pop(require_auth, None)
