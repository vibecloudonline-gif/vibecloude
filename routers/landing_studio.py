"""routers/landing_studio.py — AI Template Studio (Fase 3 del roadmap).

Panel del cliente: chat donde pega una idea y se genera la landing.
Público: /landing muestra la landing ya generada de ese tenant.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from core.limiter import limiter
from database.models import Settings, Tenant, User
from database.session import get_session
from services.ai_gateway_service import ai_gateway_service
from services.landing_service import LandingGenerationError, get_landing, save_landing
from services.settings_service import SettingsService
from web.compat_templates import CompatTemplates
from web.dependencies import get_public_tenant, get_settings, get_tenant, require_auth

router = APIRouter(tags=["Landing Studio"])

from services.plan_service import PLAN_DEFINITIONS, get_regen_limit

LANDING_REGEN_LIMITS = {slug: p["regen_limit"] for slug, p in PLAN_DEFINITIONS.items()}


def _check_regen_limit(session: Session, tenant_id: int) -> None:
    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        return
    limit = get_regen_limit(tenant.ai_tier)
    if tenant.landing_regen_count >= limit:
        raise HTTPException(
            429,
            f"Alcanzaste el limite de {limit} regeneraciones de landing para tu plan ({tenant.ai_tier}). "
            f"Upgrade tu plan para mas regeneraciones.",
        )


def _increment_regen(session: Session, tenant_id: int) -> None:
    tenant = session.get(Tenant, tenant_id)
    if tenant:
        tenant.landing_regen_count += 1
        session.add(tenant)
        session.commit()


def _templates():
    return CompatTemplates(directory="templates")


@router.get("/panel/landing", response_class=HTMLResponse)
def landing_studio_page(
    request: Request,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    import json

    SettingsService.ensure_admin(user)
    landing = get_landing(session, tenant_id)
    landing_content = json.loads(landing.content_json) if landing else None
    tenant = session.get(Tenant, tenant_id)
    regen_limit = get_regen_limit(tenant.ai_tier) if tenant else 5
    regen_used = tenant.landing_regen_count if tenant else 0
    regen_remaining = max(0, regen_limit - regen_used)
    return _templates().TemplateResponse(
        "landing_studio.html",
        {
            "request": request,
            "user": user,
            "settings": settings,
            "active_page": "landing_studio",
            "landing": landing,
            "content": landing_content,
            "regen_remaining": regen_remaining,
            "regen_limit": regen_limit,
            "regen_used": regen_used,
        },
    )


@router.post("/panel/landing/generar")
async def landing_studio_generate(
    request: Request,
    idea: str = Form(...),
    user: User = Depends(require_auth),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    SettingsService.ensure_admin(user)

    if not idea or not idea.strip():
        raise HTTPException(400, "Contame tu idea para poder generar la landing")

    _check_regen_limit(session, tenant_id)

    settings_obj = SettingsService.get_or_create_settings(session, tenant_id)
    sf_template = getattr(settings_obj, "storefront_template", None)

    try:
        content, provider_used = await ai_gateway_service.generate_landing_content_cascade(
            idea.strip(), storefront_template=sf_template,
        )
    except LandingGenerationError as exc:
        raise HTTPException(422, str(exc))

    landing = save_landing(session, tenant_id, idea.strip(), content)
    _increment_regen(session, tenant_id)
    return {
        "status": "success",
        "landing_id": landing.id,
        "content": content.model_dump(),
        "provider_used": provider_used,
        "public_url": "/landing",
    }


@router.post("/panel/landing/desde-oferta/{offer_id}")
async def landing_from_offer(
    offer_id: int,
    request: Request,
    user: User = Depends(require_auth),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    import json as _json

    from database.models import Offer
    from sqlmodel import select

    SettingsService.ensure_admin(user)

    offer = session.exec(
        select(Offer).where(Offer.id == offer_id, Offer.tenant_id == tenant_id)
    ).first()
    if not offer:
        raise HTTPException(404, "Oferta no encontrada")
    if offer.status != "validated":
        raise HTTPException(400, "La oferta debe estar validada antes de crear un sitio")

    differentiators = []
    if offer.differentiators_json:
        try:
            differentiators = _json.loads(offer.differentiators_json)
        except _json.JSONDecodeError:
            pass

    idea = (
        f"{offer.title}\n\n"
        f"Propuesta de valor: {offer.value_proposition}\n"
        f"Estructura de precio: {offer.price_structure}\n"
        f"CTA: {offer.cta_text}\n"
    )
    if differentiators:
        idea += "Diferenciadores: " + ", ".join(differentiators) + "\n"

    _check_regen_limit(session, tenant_id)

    settings_obj = SettingsService.get_or_create_settings(session, tenant_id)
    sf_template = getattr(settings_obj, "storefront_template", None)

    try:
        content, provider_used = await ai_gateway_service.generate_landing_content_cascade(
            idea, storefront_template=sf_template,
        )
    except LandingGenerationError as exc:
        raise HTTPException(422, str(exc))

    landing = save_landing(session, tenant_id, idea, content)
    _increment_regen(session, tenant_id)

    return {
        "status": "success",
        "landing_id": landing.id,
        "content": content.model_dump(),
        "provider_used": provider_used,
        "public_url": "/landing",
    }


@router.get("/landing", response_class=HTMLResponse)
@limiter.limit("30/minute")
def storefront_landing_page(
    request: Request,
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_public_tenant),
):
    import json

    from database.models import Product, Settings as SettingsModel
    from sqlmodel import select

    store_settings = session.exec(select(SettingsModel).where(SettingsModel.tenant_id == tenant_id)).first()
    if not store_settings:
        store_settings = SettingsModel(tenant_id=tenant_id, company_name="Tienda")

    products = list(session.exec(
        select(Product)
        .where(Product.tenant_id == tenant_id, Product.is_deleted == False)
        .limit(12)
    ).all())
    landing = get_landing(session, tenant_id)
    if not landing:
        return _templates().TemplateResponse(
            "storefront_landing.html",
            {"request": request, "settings": store_settings, "content": None, "products": products, "cart_count": 0},
        )

    content = json.loads(landing.content_json)
    return _templates().TemplateResponse(
        "storefront_landing.html",
        {"request": request, "settings": store_settings, "content": content, "products": products, "cart_count": 0},
    )
