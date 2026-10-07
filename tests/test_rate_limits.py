import os
os.environ["SECRET_KEY"] = "testsecretkey123"
os.environ["VIBECLOUD_API_KEY"] = "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI="

import pytest
from decimal import Decimal
from database.models import Tenant


def test_landing_regen_limits_dict():
    from routers.landing_studio import LANDING_REGEN_LIMITS
    assert LANDING_REGEN_LIMITS["inicial"] == 5
    assert LANDING_REGEN_LIMITS["tienda"] == 40
    assert LANDING_REGEN_LIMITS["comercio"] == 200


def test_tenant_landing_regen_count_default():
    t = Tenant(name="Test", subdomain="test")
    assert t.landing_regen_count == 0


def test_check_regen_limit_import():
    from routers.landing_studio import _check_regen_limit, _increment_regen
    assert callable(_check_regen_limit)
    assert callable(_increment_regen)


def test_storefront_has_limiter_import():
    from routers.storefront import limiter
    assert limiter is not None


def test_network_has_limiter_import():
    from routers.network import limiter
    assert limiter is not None


def test_courses_has_limiter_import():
    from routers.courses import limiter
    assert limiter is not None


def test_landing_studio_has_limiter_import():
    from routers.landing_studio import limiter
    assert limiter is not None


def test_limiter_core_module():
    from core.limiter import limiter, HAS_SLOWAPI
    assert HAS_SLOWAPI is True
    assert limiter is not None


def test_regen_limit_values_by_tier():
    from services.plan_service import get_regen_limit
    t_inicial = Tenant(name="Inicial", subdomain="ini", ai_tier="inicial")
    t_tienda = Tenant(name="Tienda", subdomain="tienda", ai_tier="tienda")
    t_comercio = Tenant(name="Comercio", subdomain="comercio", ai_tier="comercio")
    assert get_regen_limit(t_inicial.ai_tier) == 5
    assert get_regen_limit(t_tienda.ai_tier) == 40
    assert get_regen_limit(t_comercio.ai_tier) == 200
    # Alias viejos siguen funcionando
    assert get_regen_limit("free") == 5
    assert get_regen_limit("starter") == 40
    assert get_regen_limit("growth") == 200
