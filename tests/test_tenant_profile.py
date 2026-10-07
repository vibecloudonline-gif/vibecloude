import os
os.environ["SECRET_KEY"] = "testsecretkey123"
os.environ["VIBECLOUD_API_KEY"] = "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI="

import pytest
from unittest.mock import MagicMock
from sqlmodel import Session

from database.models import Tenant, TenantProfile
from services.ai_brain_service import AIBrainService


def _make_session_with_profile(**profile_kwargs):
    tenant = Tenant(id=1, name="Test Tenant", subdomain="test")
    profile = TenantProfile(id=1, tenant_id=1, **profile_kwargs)

    mock_session = MagicMock(spec=Session)

    def mock_exec(stmt):
        result = MagicMock()
        result.first.return_value = profile
        return result

    mock_session.exec.return_value = MagicMock(first=MagicMock(return_value=profile))
    mock_session.exec.side_effect = mock_exec
    return mock_session, profile


def test_tenant_profile_model_fields():
    p = TenantProfile(
        tenant_id=1,
        elevator_pitch="Vendemos ropa deportiva sustentable",
        business_type="physical_product",
        business_stage="launched",
        target_audience="Jovenes 18-30",
        target_market="national",
        main_challenge="Conseguir clientes",
        competitors="Nike, Adidas",
    )
    assert p.tenant_id == 1
    assert p.elevator_pitch == "Vendemos ropa deportiva sustentable"
    assert p.business_type == "physical_product"
    assert p.business_stage == "launched"
    assert p.target_audience == "Jovenes 18-30"
    assert p.target_market == "national"
    assert p.main_challenge == "Conseguir clientes"
    assert p.competitors == "Nike, Adidas"


def test_tenant_profile_defaults():
    p = TenantProfile(tenant_id=1)
    assert p.elevator_pitch == ""
    assert p.business_type == "other"
    assert p.business_stage == "idea"
    assert p.target_audience == ""
    assert p.target_market == "local"
    assert p.main_challenge == ""
    assert p.competitors is None
    assert p.monthly_revenue_target is None


def test_build_dynamic_prompt_no_profile():
    mock_session = MagicMock(spec=Session)
    mock_session.exec.return_value = MagicMock(first=MagicMock(return_value=None))
    result = AIBrainService.build_dynamic_prompt(mock_session, 1)
    assert result is None


def test_build_dynamic_prompt_empty_pitch():
    mock_session, _ = _make_session_with_profile(elevator_pitch="")
    result = AIBrainService.build_dynamic_prompt(mock_session, 1)
    assert result is None


def test_build_dynamic_prompt_with_profile():
    mock_session, _ = _make_session_with_profile(
        elevator_pitch="Vendemos cafe de especialidad",
        business_type="gastro",
        business_stage="launched",
        target_audience="Amantes del cafe en Buenos Aires",
        target_market="local",
        main_challenge="Competir con las cadenas grandes",
        competitors="Starbucks, Havanna",
    )
    result = AIBrainService.build_dynamic_prompt(mock_session, 1)
    assert result is not None
    assert "Vendemos cafe de especialidad" in result
    assert "gastronomia" in result
    assert "ya lanzado" in result
    assert "Amantes del cafe" in result
    assert "Competir con las cadenas" in result
    assert "Starbucks, Havanna" in result


def test_build_dynamic_prompt_with_revenue():
    from decimal import Decimal
    mock_session, profile = _make_session_with_profile(
        elevator_pitch="SaaS de contabilidad",
        business_type="saas",
        business_stage="scaling",
    )
    profile.monthly_revenue_target = Decimal("5000.00")
    result = AIBrainService.build_dynamic_prompt(mock_session, 1)
    assert "USD 5000" in result
    assert "SaaS" in result
    assert "escalamiento" in result
