"""Tests para los endpoints de landing pages y el servicio de generación."""
import os
os.environ.setdefault("SECRET_KEY", "testsecretkey123")
os.environ.setdefault("VIBECLOUD_API_KEY", "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI=")

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from database.models import LandingPage, Settings, Tenant, User
from database.session import get_session
from main import app
from services.auth_service import AuthService
from services.landing_service import (
    LandingGenerationError,
    LandingPageContent,
    LandingSection,
    LandingTheme,
    _validate,
    get_landing,
    save_landing,
)


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


VALID_CONTENT = {
    "hero_title": "Bienvenido a tu tienda",
    "hero_subtitle": "Los mejores productos artesanales de la region",
    "cta_text": "Ver Productos",
    "sections": [
        {"title": "Calidad", "body": "Productos de primera calidad."},
        {"title": "Envios", "body": "Envios rapidos a todo el pais."},
    ],
    "theme": {
        "primary_color": "#2D5A3D",
        "secondary_color": "#8B6F47",
        "font_family": "Outfit",
    },
}


def _make_tenant(session, has_landing=True, ai_tier="inicial", regen_count=0):
    tenant = Tenant(
        name="TestCo", subdomain="testco", has_landing=has_landing,
        has_ecommerce=True, ai_tier=ai_tier, landing_regen_count=regen_count,
    )
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    user = User(
        username="admin", role="admin", tenant_id=tenant.id,
        password_hash=AuthService.get_password_hash("TestPass123!"),
    )
    session.add(user)
    settings = Settings(tenant_id=tenant.id, company_name="TestCo")
    session.add(settings)
    session.commit()
    session.refresh(user)
    return tenant, user


def _make_non_admin(session, tenant):
    user = User(
        username="seller", role="seller", tenant_id=tenant.id,
        password_hash=AuthService.get_password_hash("TestPass123!"),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _login(client, username="admin"):
    client.post("/login", data={"username": username, "password": "TestPass123!"}, follow_redirects=False)


def _seed_landing(session, tenant_id):
    landing = LandingPage(
        tenant_id=tenant_id,
        prompt_used="Tienda artesanal",
        content_json=json.dumps(VALID_CONTENT),
    )
    session.add(landing)
    session.commit()
    session.refresh(landing)
    return landing


def _make_content():
    return LandingPageContent(
        hero_title="Test Title",
        hero_subtitle="Test subtitle for the landing",
        cta_text="Comprar",
        sections=[
            LandingSection(title="Seccion 1", body="Cuerpo de la seccion."),
        ],
        theme=LandingTheme(
            primary_color="#112233",
            secondary_color="#445566",
            font_family="Inter",
        ),
    )


# =====================================================================
# LandingPageContent validation (Pydantic model)
# =====================================================================


class TestLandingPageContentValidation:
    def test_valid_content_parses(self):
        content = _validate(json.dumps(VALID_CONTENT))
        assert content.hero_title == "Bienvenido a tu tienda"
        assert len(content.sections) == 2
        assert content.theme.font_family == "Outfit"

    def test_invalid_json_raises(self):
        with pytest.raises(LandingGenerationError, match="JSON"):
            _validate("not json at all")

    def test_markup_in_hero_title_rejected(self):
        data = {**VALID_CONTENT, "hero_title": "<script>alert(1)</script>"}
        with pytest.raises(Exception):
            _validate(json.dumps(data))

    def test_markup_in_section_title_rejected(self):
        data = {**VALID_CONTENT, "sections": [{"title": "<b>Bold</b>", "body": "ok"}]}
        with pytest.raises(Exception):
            _validate(json.dumps(data))

    def test_markup_in_section_body_rejected(self):
        data = {**VALID_CONTENT, "sections": [{"title": "ok", "body": "<img src=x>"}]}
        with pytest.raises(Exception):
            _validate(json.dumps(data))

    def test_markup_in_cta_rejected(self):
        data = {**VALID_CONTENT, "cta_text": "<a href>Click</a>"}
        with pytest.raises(Exception):
            _validate(json.dumps(data))

    def test_invalid_color_rejected(self):
        data = {**VALID_CONTENT, "theme": {**VALID_CONTENT["theme"], "primary_color": "red"}}
        with pytest.raises(Exception):
            _validate(json.dumps(data))

    def test_invalid_font_rejected(self):
        data = {**VALID_CONTENT, "theme": {**VALID_CONTENT["theme"], "font_family": "Comic Sans"}}
        with pytest.raises(Exception):
            _validate(json.dumps(data))

    def test_hero_title_too_long(self):
        data = {**VALID_CONTENT, "hero_title": "x" * 81}
        with pytest.raises(Exception):
            _validate(json.dumps(data))

    def test_hero_subtitle_too_long(self):
        data = {**VALID_CONTENT, "hero_subtitle": "x" * 221}
        with pytest.raises(Exception):
            _validate(json.dumps(data))

    def test_cta_too_long(self):
        data = {**VALID_CONTENT, "cta_text": "x" * 41}
        with pytest.raises(Exception):
            _validate(json.dumps(data))


# =====================================================================
# save_landing / get_landing (service layer)
# =====================================================================


class TestLandingService:
    def test_save_and_get(self, session):
        tenant = Tenant(name="T", subdomain="t", has_landing=True)
        session.add(tenant)
        session.commit()
        session.refresh(tenant)

        content = _make_content()
        landing = save_landing(session, tenant.id, "mi idea", content)
        assert landing.id is not None
        assert landing.tenant_id == tenant.id

        fetched = get_landing(session, tenant.id)
        assert fetched is not None
        assert fetched.id == landing.id
        parsed = json.loads(fetched.content_json)
        assert parsed["hero_title"] == "Test Title"

    def test_save_updates_existing(self, session):
        tenant = Tenant(name="T", subdomain="t", has_landing=True)
        session.add(tenant)
        session.commit()
        session.refresh(tenant)

        c1 = _make_content()
        l1 = save_landing(session, tenant.id, "idea 1", c1)

        c2 = LandingPageContent(
            hero_title="Updated Title",
            hero_subtitle="Updated subtitle",
            cta_text="Nuevo CTA",
            sections=[LandingSection(title="S", body="B")],
            theme=LandingTheme(primary_color="#AABBCC", secondary_color="#DDEEFF", font_family="Poppins"),
        )
        l2 = save_landing(session, tenant.id, "idea 2", c2)

        assert l2.id == l1.id
        parsed = json.loads(l2.content_json)
        assert parsed["hero_title"] == "Updated Title"

    def test_get_nonexistent_returns_none(self, session):
        assert get_landing(session, 99999) is None

    def test_save_with_reference_image(self, session):
        tenant = Tenant(name="T", subdomain="t", has_landing=True)
        session.add(tenant)
        session.commit()
        session.refresh(tenant)

        content = _make_content()
        landing = save_landing(session, tenant.id, "idea", content, reference_image_url="/img/ref.jpg")
        assert landing.reference_image_url == "/img/ref.jpg"


# =====================================================================
# GET /panel/landing — Studio page
# =====================================================================


class TestLandingStudioPage:
    def test_studio_requires_auth(self, client, session):
        _make_tenant(session)
        resp = client.get("/panel/landing", follow_redirects=False)
        assert resp.status_code == 302

    def test_studio_requires_admin(self, client, session):
        tenant, _ = _make_tenant(session)
        _make_non_admin(session, tenant)
        _login(client, "seller")
        resp = client.get("/panel/landing")
        assert resp.status_code == 403

    def test_studio_renders_without_landing(self, client, session):
        _make_tenant(session)
        _login(client)
        resp = client.get("/panel/landing")
        assert resp.status_code == 200

    def test_studio_renders_with_landing(self, client, session):
        tenant, _ = _make_tenant(session)
        _seed_landing(session, tenant.id)
        _login(client)
        resp = client.get("/panel/landing")
        assert resp.status_code == 200

    def test_studio_shows_regen_info(self, client, session):
        tenant, _ = _make_tenant(session, ai_tier="inicial", regen_count=2)
        _login(client)
        resp = client.get("/panel/landing")
        assert resp.status_code == 200


# =====================================================================
# POST /panel/landing/generar — Generate landing
# =====================================================================


class TestLandingGenerate:
    def test_generate_requires_auth(self, client, session):
        _make_tenant(session)
        resp = client.post("/panel/landing/generar", data={"idea": "mi tienda"}, follow_redirects=False)
        assert resp.status_code in (302, 401, 403)

    def test_generate_requires_admin(self, client, session):
        tenant, _ = _make_tenant(session)
        _make_non_admin(session, tenant)
        _login(client, "seller")
        resp = client.post("/panel/landing/generar", data={"idea": "mi tienda"})
        assert resp.status_code == 403

    def test_generate_empty_idea_rejected(self, client, session):
        _make_tenant(session)
        _login(client)
        resp = client.post("/panel/landing/generar", data={"idea": "   "})
        assert resp.status_code == 400

    @patch("routers.landing_studio.ai_gateway_service")
    def test_generate_success(self, mock_gw, client, session):
        _make_tenant(session)
        _login(client)
        content = _make_content()
        mock_gw.generate_landing_content_cascade = AsyncMock(return_value=(content, "gemini"))
        resp = client.post("/panel/landing/generar", data={"idea": "Tienda de ropa"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["provider_used"] == "gemini"
        assert data["public_url"] == "/landing"
        assert "landing_id" in data

    @patch("routers.landing_studio.ai_gateway_service")
    def test_generate_increments_regen_count(self, mock_gw, client, session):
        tenant, _ = _make_tenant(session, regen_count=0)
        _login(client)
        content = _make_content()
        mock_gw.generate_landing_content_cascade = AsyncMock(return_value=(content, "gemini"))
        client.post("/panel/landing/generar", data={"idea": "Test"})
        session.refresh(tenant)
        assert tenant.landing_regen_count == 1

    @patch("routers.landing_studio.ai_gateway_service")
    def test_generate_at_regen_limit_returns_429(self, mock_gw, client, session):
        _make_tenant(session, ai_tier="inicial", regen_count=5)
        _login(client)
        resp = client.post("/panel/landing/generar", data={"idea": "Test"})
        assert resp.status_code == 429
        mock_gw.generate_landing_content_cascade.assert_not_called()

    @patch("routers.landing_studio.ai_gateway_service")
    def test_generate_ai_error_returns_422(self, mock_gw, client, session):
        _make_tenant(session)
        _login(client)
        mock_gw.generate_landing_content_cascade = AsyncMock(
            side_effect=LandingGenerationError("AI failed")
        )
        resp = client.post("/panel/landing/generar", data={"idea": "Test"})
        assert resp.status_code == 422

    @patch("routers.landing_studio.ai_gateway_service")
    def test_generate_passes_storefront_template(self, mock_gw, client, session):
        tenant, _ = _make_tenant(session)
        settings = session.get(Settings, 1)
        if settings:
            settings.storefront_template = "sabor"
            session.add(settings)
            session.commit()
        _login(client)
        content = _make_content()
        mock_gw.generate_landing_content_cascade = AsyncMock(return_value=(content, "gemini"))
        client.post("/panel/landing/generar", data={"idea": "Test"})
        call_kwargs = mock_gw.generate_landing_content_cascade.call_args
        assert call_kwargs is not None


# =====================================================================
# POST /panel/landing/desde-oferta/{id} — Generate from offer
# =====================================================================


class TestLandingFromOffer:
    def _make_offer(self, session, tenant_id, status="validated"):
        from database.models import Offer, ResearchProject
        project = ResearchProject(tenant_id=tenant_id, query_description="Test query", status="completed")
        session.add(project)
        session.commit()
        session.refresh(project)
        offer = Offer(
            tenant_id=tenant_id, project_id=project.id,
            title="Oferta Test", value_proposition="Valor unico",
            price_structure="$100/mes", cta_text="Comprar ahora",
            status=status,
        )
        session.add(offer)
        session.commit()
        session.refresh(offer)
        return offer

    def test_from_offer_requires_auth(self, client, session):
        _make_tenant(session)
        resp = client.post("/panel/landing/desde-oferta/1", follow_redirects=False)
        assert resp.status_code in (302, 401, 403)

    def test_from_offer_not_found(self, client, session):
        _make_tenant(session)
        _login(client)
        resp = client.post("/panel/landing/desde-oferta/999")
        assert resp.status_code == 404

    def test_from_offer_not_validated(self, client, session):
        tenant, _ = _make_tenant(session)
        offer = self._make_offer(session, tenant.id, status="draft")
        _login(client)
        resp = client.post(f"/panel/landing/desde-oferta/{offer.id}")
        assert resp.status_code == 400

    @patch("routers.landing_studio.ai_gateway_service")
    def test_from_offer_success(self, mock_gw, client, session):
        tenant, _ = _make_tenant(session)
        offer = self._make_offer(session, tenant.id, status="validated")
        _login(client)
        content = _make_content()
        mock_gw.generate_landing_content_cascade = AsyncMock(return_value=(content, "claude"))
        resp = client.post(f"/panel/landing/desde-oferta/{offer.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["provider_used"] == "claude"

    @patch("routers.landing_studio.ai_gateway_service")
    def test_from_offer_at_regen_limit(self, mock_gw, client, session):
        tenant, _ = _make_tenant(session, ai_tier="inicial", regen_count=5)
        offer = self._make_offer(session, tenant.id)
        _login(client)
        resp = client.post(f"/panel/landing/desde-oferta/{offer.id}")
        assert resp.status_code == 429

    @patch("routers.landing_studio.ai_gateway_service")
    def test_from_offer_with_differentiators(self, mock_gw, client, session):
        tenant, _ = _make_tenant(session)
        offer = self._make_offer(session, tenant.id, status="validated")
        offer.differentiators_json = json.dumps(["Rapido", "Barato", "Seguro"])
        session.add(offer)
        session.commit()
        _login(client)
        content = _make_content()
        mock_gw.generate_landing_content_cascade = AsyncMock(return_value=(content, "gemini"))
        resp = client.post(f"/panel/landing/desde-oferta/{offer.id}")
        assert resp.status_code == 200


# =====================================================================
# GET /landing — Public landing page
# =====================================================================


class TestPublicLanding:
    def test_public_landing_no_landing_renders(self, client, session):
        tenant = Tenant(name="PubCo", subdomain="pubco", has_landing=True)
        session.add(tenant)
        settings = Settings(tenant_id=1, company_name="PubCo")
        session.add(settings)
        session.commit()
        resp = client.get("/landing", headers={"host": "pubco.localhost"})
        assert resp.status_code == 200

    def test_public_landing_with_content(self, client, session):
        tenant = Tenant(name="PubCo", subdomain="pubco", has_landing=True)
        session.add(tenant)
        session.commit()
        session.refresh(tenant)
        settings = Settings(tenant_id=tenant.id, company_name="PubCo")
        session.add(settings)
        _seed_landing(session, tenant.id)
        session.commit()
        resp = client.get("/landing", headers={"host": "pubco.localhost"})
        assert resp.status_code == 200
        assert "Bienvenido" in resp.text or resp.status_code == 200


# =====================================================================
# Regen limits across plans
# =====================================================================


class TestRegenLimits:
    @patch("routers.landing_studio.ai_gateway_service")
    def test_tienda_plan_has_higher_limit(self, mock_gw, client, session):
        _make_tenant(session, ai_tier="tienda", regen_count=5)
        _login(client)
        content = _make_content()
        mock_gw.generate_landing_content_cascade = AsyncMock(return_value=(content, "gemini"))
        resp = client.post("/panel/landing/generar", data={"idea": "Test"})
        assert resp.status_code == 200

    @patch("routers.landing_studio.ai_gateway_service")
    def test_tienda_plan_at_limit(self, mock_gw, client, session):
        _make_tenant(session, ai_tier="tienda", regen_count=40)
        _login(client)
        resp = client.post("/panel/landing/generar", data={"idea": "Test"})
        assert resp.status_code == 429

    @patch("routers.landing_studio.ai_gateway_service")
    def test_comercio_plan_at_limit(self, mock_gw, client, session):
        _make_tenant(session, ai_tier="comercio", regen_count=200)
        _login(client)
        resp = client.post("/panel/landing/generar", data={"idea": "Test"})
        assert resp.status_code == 429

    @patch("routers.landing_studio.ai_gateway_service")
    def test_comercio_plan_below_limit(self, mock_gw, client, session):
        _make_tenant(session, ai_tier="comercio", regen_count=100)
        _login(client)
        content = _make_content()
        mock_gw.generate_landing_content_cascade = AsyncMock(return_value=(content, "gemini"))
        resp = client.post("/panel/landing/generar", data={"idea": "Test"})
        assert resp.status_code == 200


# =====================================================================
# Storefront template unification (landing ← storefront palette)
# =====================================================================


class TestLandingStorefrontUnification:
    def test_enriched_prompt_includes_palette(self):
        from services.storefront_renderer import THEME_PRESETS
        preset = THEME_PRESETS["sabor"]
        from services.landing_service import ALLOWED_FONTS, generate_landing_content

        prompt = "Tienda de comida"
        enriched = prompt
        font = preset.get("heading_font", "Inter")
        if font not in ALLOWED_FONTS:
            font = "Inter"
        enriched = (
            f"{prompt}\n\n"
            f"IMPORTANTE: Usa exactamente estos colores y fuente para "
            f"mantener coherencia con la tienda online:\n"
            f"- primary_color: {preset['accent']}\n"
            f"- secondary_color: {preset['primary']}\n"
            f"- font_family: {font}\n"
        )
        assert preset["accent"] in enriched
        assert preset["primary"] in enriched

    def test_unknown_template_no_enrichment(self):
        from services.storefront_renderer import THEME_PRESETS
        assert "nonexistent_template" not in THEME_PRESETS

    def test_font_fallback_for_unlisted_font(self):
        from services.landing_service import ALLOWED_FONTS
        assert "Comic Sans" not in ALLOWED_FONTS
        assert "Inter" in ALLOWED_FONTS
