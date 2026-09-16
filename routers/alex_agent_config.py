from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select

from database.models import AlexAgentContext, Offer, Settings, Tenant, User
from database.session import get_session
from web.compat_templates import CompatTemplates
from web.dependencies import get_settings, get_tenant, require_auth

router = APIRouter(tags=["Alex Agent Config"])


def _templates():
    return CompatTemplates(directory="templates")


@router.get("/panel/alex-agent", response_class=HTMLResponse)
def alex_agent_page(
    request: Request,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    tenant = session.get(Tenant, tenant_id)
    if not tenant or not tenant.has_alexio:
        raise HTTPException(403, "Tu cuenta no tiene AlexIO contratado")

    ctx = session.exec(
        select(AlexAgentContext).where(AlexAgentContext.tenant_id == tenant_id)
    ).first()

    validated_offers = session.exec(
        select(Offer).where(Offer.tenant_id == tenant_id, Offer.status == "validated")
    ).all()

    faq_entries = []
    if ctx and ctx.faq_entries_json:
        try:
            faq_entries = json.loads(ctx.faq_entries_json)
        except (json.JSONDecodeError, TypeError):
            pass

    return _templates().TemplateResponse(
        "panel_alex_agent.html",
        {
            "request": request,
            "user": user,
            "settings": settings,
            "context": ctx,
            "validated_offers": validated_offers,
            "faq_entries": faq_entries,
            "view": "alex_agent",
        },
    )


@router.post("/panel/alex-agent/guardar")
def alex_agent_save(
    request: Request,
    personality_tone: str = Form("profesional_cercano"),
    business_description: str = Form(""),
    validated_offer_id: str = Form(""),
    custom_instructions: str = Form(""),
    faq_json: str = Form("[]"),
    user: User = Depends(require_auth),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    tenant = session.get(Tenant, tenant_id)
    if not tenant or not tenant.has_alexio:
        raise HTTPException(403, "Tu cuenta no tiene AlexIO contratado")

    valid_tones = ("profesional_cercano", "formal", "casual", "tecnico")
    if personality_tone not in valid_tones:
        raise HTTPException(400, "Tono invalido")

    offer_id = None
    if validated_offer_id.strip():
        try:
            offer_id = int(validated_offer_id)
            offer = session.exec(
                select(Offer).where(Offer.id == offer_id, Offer.tenant_id == tenant_id, Offer.status == "validated")
            ).first()
            if not offer:
                raise HTTPException(400, "Oferta no encontrada o no validada")
        except ValueError:
            raise HTTPException(400, "ID de oferta invalido")

    try:
        faq_entries = json.loads(faq_json)
        if not isinstance(faq_entries, list):
            faq_entries = []
    except (json.JSONDecodeError, TypeError):
        faq_entries = []

    ctx = session.exec(
        select(AlexAgentContext).where(AlexAgentContext.tenant_id == tenant_id)
    ).first()

    if ctx:
        ctx.personality_tone = personality_tone
        ctx.business_description = business_description.strip() or None
        ctx.validated_offer_id = offer_id
        ctx.custom_instructions = custom_instructions.strip() or None
        ctx.faq_entries_json = json.dumps(faq_entries, ensure_ascii=False) if faq_entries else None
    else:
        ctx = AlexAgentContext(
            tenant_id=tenant_id,
            personality_tone=personality_tone,
            business_description=business_description.strip() or None,
            validated_offer_id=offer_id,
            custom_instructions=custom_instructions.strip() or None,
            faq_entries_json=json.dumps(faq_entries, ensure_ascii=False) if faq_entries else None,
        )

    session.add(ctx)
    session.commit()
    return {"status": "success"}
