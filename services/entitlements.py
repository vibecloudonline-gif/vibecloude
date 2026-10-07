"""Entitlements — única fuente de verdad para "¿puede este tenant usar el módulo X?"

Combina el nivel del tenant (1-3) con overrides de superadmin (has_*).
Los routers llaman a can_use_module() en vez de chequear has_* directamente.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from database.models import Tenant

MODULE_LEVELS: dict[str, int] = {
    # Nivel 1 — Arranque (disponible desde el registro)
    "landing": 1,
    "landing_studio": 1,
    "storefront": 1,
    "store": 1,
    "products": 1,
    "catalog_import": 1,
    "catalog_manage": 1,
    "payments": 1,
    "sales": 1,
    "pos": 1,
    "wms": 1,
    "cash": 1,
    "clients": 1,
    "reports": 1,
    "team": 1,
    "ai": 1,
    "onboarding": 1,
    "social_content": 1,
    "domains": 1,
    # Nivel 2 — Inteligencia (tienda publicada + primeras ventas)
    "research": 2,
    "competitor": 2,
    "expert_debate": 2,
    "offer": 2,
    "debate": 2,
    "forecast": 2,
    "timesfm": 2,
    # Nivel 3 — Comunidad (ventas sostenidas + confianza)
    "network": 3,
    "courses": 3,
    "picking": 3,
    "crm": 3,
}

_MODULE_HAS_FLAG: dict[str, str] = {
    "sales": "has_erp",
    "pos": "has_erp",
    "wms": "has_erp",
    "cash": "has_erp",
    "clients": "has_erp",
    "reports": "has_erp",
    "picking": "has_erp",
    "storefront": "has_ecommerce",
    "store": "has_ecommerce",
    "payments": "has_ecommerce",
    "landing": "has_landing",
    "landing_studio": "has_landing",
    "courses": "has_courses",
}

LEVEL_NAMES: dict[int, str] = {
    1: "Arranque",
    2: "Inteligencia",
    3: "Comunidad",
}

LEVEL_REQUIREMENTS: dict[int, str] = {
    2: "Tienda publicada y primeras ventas",
    3: "Ventas sostenidas y métricas de confianza limpias",
}

UPGRADE_THRESHOLDS: dict[int, dict] = {
    2: {"min_sales": 1, "store_published": True},
    3: {"min_sales": 20, "trust_score_min": 0.7},
}


def can_use_module(tenant: "Tenant", module: str) -> bool:
    required_level = MODULE_LEVELS.get(module)
    if required_level is None:
        return True

    if tenant.nivel < required_level:
        return False

    flag_name = _MODULE_HAS_FLAG.get(module)
    if flag_name and not getattr(tenant, flag_name, True):
        return False

    return True


def get_blocked_message(module: str) -> str:
    required_level = MODULE_LEVELS.get(module)
    if required_level is None:
        return ""
    level_name = LEVEL_NAMES.get(required_level, f"Nivel {required_level}")
    requirement = LEVEL_REQUIREMENTS.get(required_level, "")
    if requirement:
        return f"Este módulo se habilita en el nivel «{level_name}». Requisito: {requirement}."
    return f"Este módulo requiere el nivel «{level_name}»."


def get_enabled_modules(tenant: "Tenant") -> list[str]:
    return [m for m in MODULE_LEVELS if can_use_module(tenant, m)]


def get_disabled_modules(tenant: "Tenant") -> list[str]:
    return [m for m in MODULE_LEVELS if not can_use_module(tenant, m)]


def check_upgrade_eligibility(tenant: "Tenant", total_sales: int, store_published: bool, trust_score: float) -> int | None:
    """Devuelve el nivel al que podría subir, o None si ya está en el máximo o no cumple."""
    next_level = tenant.nivel + 1
    thresholds = UPGRADE_THRESHOLDS.get(next_level)
    if not thresholds:
        return None

    if total_sales < thresholds.get("min_sales", 0):
        return None
    if thresholds.get("store_published") and not store_published:
        return None
    if trust_score < thresholds.get("trust_score_min", 0):
        return None

    return next_level
