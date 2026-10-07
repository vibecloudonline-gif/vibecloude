"""services/plan_service.py — Fuente única de verdad para planes y sus límites.

Todos los límites de la sección 1.3 de CLAUDE.md viven acá.
Otros módulos (payments, landing_studio, storage_service) importan de acá.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlmodel import Session, func, select


PLAN_DEFINITIONS: dict[str, dict] = {
    "inicial": {
        "label": "Inicial",
        "price": Decimal("3.97"),
        "credits_per_month": 30,
        "regen_limit": 5,
        "max_products": 30,
        "storage_bytes": 250 * 1024 * 1024,       # 250 MB
        "max_users": 1,
        "includes": "Sitio con IA, catálogo, pedidos por WhatsApp (sin checkout)",
    },
    "tienda": {
        "label": "Tienda",
        "price": Decimal("19.00"),
        "credits_per_month": 500,
        "regen_limit": 40,
        "max_products": None,  # sin límite
        "storage_bytes": 2 * 1024 * 1024 * 1024,   # 2 GB
        "max_users": 1,
        "includes": "+ tienda con checkout",
    },
    "comercio": {
        "label": "Comercio",
        "price": Decimal("49.00"),
        "credits_per_month": 2000,
        "regen_limit": 200,
        "max_products": None,  # sin límite
        "storage_bytes": 10 * 1024 * 1024 * 1024,  # 10 GB
        "max_users": 5,
        "includes": "+ POS, stock, caja, cuentas corrientes, reportes, equipo, dominio propio",
    },
}

# Compatibilidad: nombres viejos → nuevos (para tenants que aún tengan ai_tier viejo)
_TIER_ALIASES: dict[str, str] = {
    "free": "inicial",
    "starter": "tienda",
    "growth": "comercio",
}


def resolve_tier(ai_tier: str) -> str:
    return _TIER_ALIASES.get(ai_tier, ai_tier)


def get_plan(ai_tier: str) -> dict:
    tier = resolve_tier(ai_tier)
    return PLAN_DEFINITIONS.get(tier, PLAN_DEFINITIONS["inicial"])


def get_plan_price(ai_tier: str) -> Decimal:
    return get_plan(ai_tier)["price"]


def get_plan_label(ai_tier: str) -> str:
    return get_plan(ai_tier)["label"]


def get_credits_per_month(ai_tier: str) -> int:
    return get_plan(ai_tier)["credits_per_month"]


def get_regen_limit(ai_tier: str) -> int:
    return get_plan(ai_tier)["regen_limit"]


def get_max_products(ai_tier: str) -> Optional[int]:
    return get_plan(ai_tier)["max_products"]


def get_storage_limit(ai_tier: str) -> int:
    return get_plan(ai_tier)["storage_bytes"]


def get_max_users(ai_tier: str) -> int:
    return get_plan(ai_tier)["max_users"]


def check_product_limit(session: Session, tenant_id: int, ai_tier: str) -> bool:
    """True si el tenant puede agregar un producto más. False si alcanzó el límite."""
    from database.models import Product
    limit = get_max_products(ai_tier)
    if limit is None:
        return True
    count = session.exec(
        select(func.count(Product.id)).where(
            Product.tenant_id == tenant_id,
            Product.is_deleted == False,  # noqa: E712
        )
    ).one()
    return count < limit


def check_user_limit(session: Session, tenant_id: int, ai_tier: str) -> bool:
    """True si el tenant puede agregar un usuario más. False si alcanzó el límite."""
    from database.models import User
    limit = get_max_users(ai_tier)
    count = session.exec(
        select(func.count(User.id)).where(
            User.tenant_id == tenant_id,
            User.is_deleted == False,  # noqa: E712
        )
    ).one()
    return count < limit


def get_product_count(session: Session, tenant_id: int) -> int:
    from database.models import Product
    return session.exec(
        select(func.count(Product.id)).where(
            Product.tenant_id == tenant_id,
            Product.is_deleted == False,  # noqa: E712
        )
    ).one()


def get_user_count(session: Session, tenant_id: int) -> int:
    from database.models import User
    return session.exec(
        select(func.count(User.id)).where(
            User.tenant_id == tenant_id,
            User.is_deleted == False,  # noqa: E712
        )
    ).one()


def deduct_credits_atomic(session: Session, tenant_id: int, cost: int) -> bool:
    """Descuenta créditos atómicamente. Devuelve True si se descontó, False si no hay suficientes."""
    from sqlalchemy import update as sa_update
    from database.models import Tenant

    result = session.execute(
        sa_update(Tenant)
        .where(Tenant.id == tenant_id, Tenant.ai_credits >= cost)
        .values(ai_credits=Tenant.ai_credits - cost)
    )
    session.commit()
    return result.rowcount > 0


def get_plan_usage(session: Session, tenant_id: int, ai_tier: str) -> dict:
    """Devuelve un dict con el uso actual vs límites del plan."""
    from services.storage_service import get_tenant_usage

    plan = get_plan(ai_tier)
    product_count = get_product_count(session, tenant_id)
    user_count = get_user_count(session, tenant_id)
    storage_used = get_tenant_usage(session, tenant_id)

    from database.models import Tenant
    tenant = session.get(Tenant, tenant_id)
    credits_remaining = tenant.ai_credits if tenant else 0
    regen_used = tenant.landing_regen_count if tenant else 0

    return {
        "plan_slug": resolve_tier(ai_tier),
        "plan_label": plan["label"],
        "plan_price": plan["price"],
        "plan_includes": plan["includes"],
        "credits_per_month": plan["credits_per_month"],
        "credits_remaining": credits_remaining,
        "regen_limit": plan["regen_limit"],
        "regen_used": regen_used,
        "max_products": plan["max_products"],
        "product_count": product_count,
        "storage_limit": plan["storage_bytes"],
        "storage_used": storage_used,
        "max_users": plan["max_users"],
        "user_count": user_count,
    }
