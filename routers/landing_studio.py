"""routers/landing_studio.py — AI Template Studio (Fase 3 del roadmap).

Panel del cliente: chat donde pega una idea y se genera la landing.
Público: /landing muestra la landing ya generada de ese tenant.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from core.config import settings as app_settings
from database.models import Settings, User
from database.session import get_session
from services.landing_service import (
    LandingGenerationError,
    LandingPageContent,
    generate_landing_content,
    get_landing,
    save_landing,
)
from services.settings_service import SettingsService
from web.compat_templates import CompatTemplates
from web.dependencies import get_public_tenant, get_settings, get_tenant, require_auth

router = APIRouter(tags=["Landing Studio"])


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
    return _templates().TemplateResponse(
        "landing_studio.html",
        {
            "request": request,
            "user": user,
            "settings": settings,
            "active_page": "landing_studio",
            "landing": landing,
            "content": landing_content,
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

    if not app_settings.GEMINI_API_KEY:
        raise HTTPException(400, "GEMINI_API_KEY no configurada en el servidor")
    if not idea or not idea.strip():
        raise HTTPException(400, "Contame tu idea para poder generar la landing")

    try:
        content: LandingPageContent = await generate_landing_content(idea.strip(), app_settings.GEMINI_API_KEY)
    except LandingGenerationError as exc:
        raise HTTPException(422, str(exc))

    landing = save_landing(session, tenant_id, idea.strip(), content)
    return {
        "status": "success",
        "landing_id": landing.id,
        "content": content.model_dump(),
        "public_url": "/landing",
    }


@router.get("/landing", response_class=HTMLResponse)
def storefront_landing_page(
    request: Request,
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_public_tenant),
):
    import json

    from database.models import Settings as SettingsModel
    from sqlmodel import select

    store_settings = session.exec(select(SettingsModel).where(SettingsModel.tenant_id == tenant_id)).first()
    if not store_settings:
        store_settings = SettingsModel(tenant_id=tenant_id, company_name="Tienda")

    landing = get_landing(session, tenant_id)
    if not landing:
        return _templates().TemplateResponse(
            "storefront_landing.html",
            {"request": request, "settings": store_settings, "content": None, "cart_count": 0},
        )

    content = json.loads(landing.content_json)
    return _templates().TemplateResponse(
        "storefront_landing.html",
        {"request": request, "settings": store_settings, "content": content, "cart_count": 0},
    )
