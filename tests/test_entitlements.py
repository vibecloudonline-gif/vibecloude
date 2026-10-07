"""Tests de Fase 1 — Niveles y entitlements."""
import os
os.environ.setdefault("SECRET_KEY", "testsecretkey123_for_entitlements!")
os.environ.setdefault("VIBECLOUD_API_KEY", "test-key-entitlements")

import pytest
from datetime import datetime, timezone
from sqlmodel import Session, SQLModel, create_engine, select
from database.models import Tenant
from services.entitlements import (
    MODULE_LEVELS,
    can_use_module,
    get_blocked_message,
    get_enabled_modules,
    get_disabled_modules,
    check_upgrade_eligibility,
)


@pytest.fixture
def engine():
    e = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(e)
    return e


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


def _make_tenant(session, nivel=1, **kwargs):
    defaults = {
        "name": "TestTenant",
        "subdomain": f"test{nivel}",
        "is_active": True,
        "nivel": nivel,
        "has_erp": True,
        "has_ecommerce": True,
        "has_landing": True,
        "has_courses": True,
    }
    defaults.update(kwargs)
    t = Tenant(**defaults)
    session.add(t)
    session.commit()
    session.refresh(t)
    return t


class TestModuleLevels:
    def test_all_modules_have_levels(self):
        assert len(MODULE_LEVELS) >= 30

    def test_level1_modules(self):
        assert MODULE_LEVELS["landing"] == 1
        assert MODULE_LEVELS["storefront"] == 1
        assert MODULE_LEVELS["pos"] == 1
        assert MODULE_LEVELS["ai"] == 1

    def test_level2_modules(self):
        assert MODULE_LEVELS["research"] == 2
        assert MODULE_LEVELS["expert_debate"] == 2
        assert MODULE_LEVELS["forecast"] == 2

    def test_level3_modules(self):
        assert MODULE_LEVELS["courses"] == 3
        assert MODULE_LEVELS["network"] == 3
        assert MODULE_LEVELS["crm"] == 3


class TestCanUseModule:
    def test_nivel1_can_use_level1(self, session):
        t = _make_tenant(session, nivel=1)
        assert can_use_module(t, "landing") is True
        assert can_use_module(t, "storefront") is True
        assert can_use_module(t, "pos") is True

    def test_nivel1_cannot_use_level2(self, session):
        t = _make_tenant(session, nivel=1, subdomain="test1b")
        assert can_use_module(t, "research") is False
        assert can_use_module(t, "expert_debate") is False
        assert can_use_module(t, "forecast") is False

    def test_nivel1_cannot_use_level3(self, session):
        t = _make_tenant(session, nivel=1, subdomain="test1c")
        assert can_use_module(t, "courses") is False
        assert can_use_module(t, "network") is False
        assert can_use_module(t, "crm") is False

    def test_nivel2_can_use_level1_and_2(self, session):
        t = _make_tenant(session, nivel=2, subdomain="test2")
        assert can_use_module(t, "landing") is True
        assert can_use_module(t, "research") is True
        assert can_use_module(t, "forecast") is True

    def test_nivel2_cannot_use_level3(self, session):
        t = _make_tenant(session, nivel=2, subdomain="test2b")
        assert can_use_module(t, "courses") is False
        assert can_use_module(t, "network") is False

    def test_nivel3_can_use_all(self, session):
        t = _make_tenant(session, nivel=3, subdomain="test3")
        assert can_use_module(t, "landing") is True
        assert can_use_module(t, "research") is True
        assert can_use_module(t, "courses") is True
        assert can_use_module(t, "network") is True
        assert can_use_module(t, "crm") is True

    def test_has_flag_override(self, session):
        t = _make_tenant(session, nivel=1, subdomain="test_flag", has_erp=False)
        assert can_use_module(t, "pos") is False
        assert can_use_module(t, "landing") is True

    def test_unknown_module_allowed(self, session):
        t = _make_tenant(session, nivel=1, subdomain="test_unk")
        assert can_use_module(t, "nonexistent_module") is True


class TestBlockedMessage:
    def test_level2_message(self):
        msg = get_blocked_message("research")
        assert "Inteligencia" in msg
        assert "Tienda publicada" in msg

    def test_level3_message(self):
        msg = get_blocked_message("courses")
        assert "Comunidad" in msg
        assert "Ventas sostenidas" in msg

    def test_unknown_module(self):
        msg = get_blocked_message("nonexistent")
        assert msg == ""


class TestModuleLists:
    def test_enabled_modules_nivel1(self, session):
        t = _make_tenant(session, nivel=1, subdomain="list1")
        enabled = get_enabled_modules(t)
        assert "landing" in enabled
        assert "research" not in enabled
        assert "courses" not in enabled

    def test_disabled_modules_nivel1(self, session):
        t = _make_tenant(session, nivel=1, subdomain="list1b")
        disabled = get_disabled_modules(t)
        assert "research" in disabled
        assert "courses" in disabled
        assert "landing" not in disabled


class TestUpgradeEligibility:
    def test_level1_to_2_eligible(self, session):
        t = _make_tenant(session, nivel=1, subdomain="up1")
        result = check_upgrade_eligibility(t, total_sales=5, store_published=True, trust_score=0.0)
        assert result == 2

    def test_level1_to_2_not_eligible_no_sales(self, session):
        t = _make_tenant(session, nivel=1, subdomain="up1b")
        result = check_upgrade_eligibility(t, total_sales=0, store_published=True, trust_score=0.0)
        assert result is None

    def test_level1_to_2_not_eligible_no_store(self, session):
        t = _make_tenant(session, nivel=1, subdomain="up1c")
        result = check_upgrade_eligibility(t, total_sales=5, store_published=False, trust_score=0.0)
        assert result is None

    def test_level2_to_3_eligible(self, session):
        t = _make_tenant(session, nivel=2, subdomain="up2")
        result = check_upgrade_eligibility(t, total_sales=25, store_published=True, trust_score=0.8)
        assert result == 3

    def test_level2_to_3_low_trust(self, session):
        t = _make_tenant(session, nivel=2, subdomain="up2b")
        result = check_upgrade_eligibility(t, total_sales=25, store_published=True, trust_score=0.5)
        assert result is None

    def test_level3_no_upgrade(self, session):
        t = _make_tenant(session, nivel=3, subdomain="up3")
        result = check_upgrade_eligibility(t, total_sales=100, store_published=True, trust_score=1.0)
        assert result is None


class TestTenantNivelField:
    def test_default_nivel(self, session):
        t = Tenant(name="Default", subdomain="defnivel", is_active=True)
        session.add(t)
        session.commit()
        session.refresh(t)
        assert t.nivel == 1
        assert t.nivel_since is not None

    def test_custom_nivel(self, session):
        t = Tenant(name="Custom", subdomain="custnivel", is_active=True, nivel=2)
        session.add(t)
        session.commit()
        session.refresh(t)
        assert t.nivel == 2


class TestToolModuleGating:
    """Tests que los tools de AlexIO se filtran según entitlements del tenant."""

    def test_allowed_tools_nivel1_with_erp(self, session):
        from services.ai_brain_service import _get_allowed_tools_for_tenant
        t = _make_tenant(session, nivel=1, subdomain="tools1", has_erp=True)
        tools = _get_allowed_tools_for_tenant(t)
        assert "consultar_stock" in tools
        assert "recomendar_productos" in tools
        assert "obtener_metricas_ventas" in tools

    def test_allowed_tools_nivel1_without_erp(self, session):
        from services.ai_brain_service import _get_allowed_tools_for_tenant
        t = _make_tenant(session, nivel=1, subdomain="tools2", has_erp=False)
        tools = _get_allowed_tools_for_tenant(t)
        assert "consultar_stock" not in tools
        assert "obtener_metricas_ventas" not in tools
        assert "recomendar_productos" in tools

    def test_tool_module_map_covers_all_tools(self):
        from services.ai_brain_service import TOOL_MODULE_MAP
        assert "consultar_stock" in TOOL_MODULE_MAP
        assert "recomendar_productos" in TOOL_MODULE_MAP
        assert "obtener_metricas_ventas" in TOOL_MODULE_MAP

    def test_execute_tool_rejects_disabled_module(self, session):
        import asyncio
        from services.ai_brain_service import AIBrainService
        t = _make_tenant(session, nivel=1, subdomain="tools3", has_erp=False)
        result = asyncio.run(
            AIBrainService._execute_tool(session, t.id, "consultar_stock", {"product_id": 1})
        )
        assert "error" in result
        assert "plan" in result["error"].lower() or "módulo" in result["error"]

    def test_execute_tool_allows_enabled_module(self, session):
        import asyncio
        from services.ai_brain_service import AIBrainService
        t = _make_tenant(session, nivel=1, subdomain="tools4", has_erp=True)
        result = asyncio.run(
            AIBrainService._execute_tool(session, t.id, "consultar_stock", {"product_id": 999})
        )
        assert "error" in result
        assert "not found" in result["error"].lower() or "Product" in result["error"]


class TestTenantLevelsReport:
    """Tests para el endpoint de reporte de niveles SuperAdmin."""

    def test_report_endpoint_registered(self):
        from routers.superadmin import router
        paths = [r.path for r in router.routes]
        assert "/api/v1/superadmin/tenant-levels" in paths

    def test_report_returns_tenant_data(self, session):
        from services.entitlements import get_enabled_modules, get_disabled_modules, LEVEL_NAMES
        t = _make_tenant(session, nivel=2, subdomain="report1")
        enabled = get_enabled_modules(t)
        disabled = get_disabled_modules(t)
        assert "research" in enabled
        assert "courses" in disabled
        assert LEVEL_NAMES[2] == "Inteligencia"


class TestDeadCodeRemoved:
    def test_hub_html_deleted(self):
        import os
        hub_path = os.path.join(os.path.dirname(__file__), "..", "templates", "hub.html")
        assert not os.path.exists(hub_path), "templates/hub.html should be deleted"

    def test_no_services_llm(self):
        import os
        llm_path = os.path.join(os.path.dirname(__file__), "..", "services", "llm")
        assert not os.path.exists(llm_path), "services/llm/ should be deleted"

    def test_no_services_voice(self):
        import os
        voice_path = os.path.join(os.path.dirname(__file__), "..", "services", "voice")
        assert not os.path.exists(voice_path), "services/voice/ should be deleted"

    def test_no_provider_factory(self):
        import os
        pf_path = os.path.join(os.path.dirname(__file__), "..", "services", "provider_factory.py")
        assert not os.path.exists(pf_path), "services/provider_factory.py should be deleted"
