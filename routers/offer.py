from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from database.models import Offer, Settings, Tenant, User
from database.session import get_session
from web.compat_templates import CompatTemplates
from web.dependencies import get_settings, get_tenant, require_auth

router = APIRouter(tags=["Offer"])


def _templates():
    return CompatTemplates(directory="templates")


def _require_access(tenant: Tenant):
    if not (tenant.has_landing or tenant.has_ecommerce):
        raise HTTPException(403, "Tu cuenta no tiene acceso a este modulo")


@router.get("/panel/oferta/{project_id}", response_class=HTMLResponse)
def offer_page(
    project_id: int,
    request: Request,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    from services.offer_service import get_latest_offer_for_project
    from services.research_service import get_project_with_results

    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404)
    _require_access(tenant)

    project = get_project_with_results(session, project_id, tenant_id)
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")

    offer = get_latest_offer_for_project(session, project_id, tenant_id)

    differentiators = []
    if offer and offer.differentiators_json:
        try:
            differentiators = json.loads(offer.differentiators_json)
        except json.JSONDecodeError:
            pass

    return _templates().TemplateResponse(
        "panel_oferta.html",
        {
            "request": request,
            "user": user,
            "settings": settings,
            "project": project,
            "offer": offer,
            "differentiators": differentiators,
            "active_page": "oferta",
        },
    )


@router.post("/panel/oferta/{project_id}/generar")
async def offer_generate(
    project_id: int,
    request: Request,
    user: User = Depends(require_auth),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    from services.offer_service import generate_offer
    from services.research_service import get_project_with_results

    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404)
    _require_access(tenant)

    project = get_project_with_results(session, project_id, tenant_id)
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")
    if project.status != "completed":
        raise HTTPException(400, "El proyecto debe estar completo antes de generar una oferta")

    try:
        offer = await generate_offer(session, project, tenant_id)
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))

    return {"status": "success", "offer_id": offer.id}


@router.post("/panel/oferta/{offer_id}/validar")
async def offer_validate(
    offer_id: int,
    request: Request,
    user: User = Depends(require_auth),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    from services.debate_service import run_debate
    from services.offer_service import get_offer

    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404)
    _require_access(tenant)

    offer = get_offer(session, offer_id, tenant_id)
    if not offer:
        raise HTTPException(404, "Oferta no encontrada")
    if offer.status not in ("draft", "rejected"):
        raise HTTPException(400, "Esta oferta ya fue validada")

    offer.status = "pending_validation"
    session.add(offer)
    session.commit()

    try:
        debate = await run_debate(session, offer)
    except Exception as exc:
        offer.status = "draft"
        session.add(offer)
        session.commit()
        raise HTTPException(500, f"Error en debate: {exc}")

    return {
        "status": "success",
        "debate_id": debate.id,
        "verdict": debate.final_verdict,
    }


@router.get("/panel/oferta/{offer_id}/debate", response_class=HTMLResponse)
def debate_detail(
    offer_id: int,
    request: Request,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    from services.offer_service import get_offer

    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404)
    _require_access(tenant)

    offer = get_offer(session, offer_id, tenant_id)
    if not offer:
        raise HTTPException(404, "Oferta no encontrada")

    debate = offer.debate
    objections = debate.objections if debate else []

    return _templates().TemplateResponse(
        "panel_debate.html",
        {
            "request": request,
            "user": user,
            "settings": settings,
            "offer": offer,
            "debate": debate,
            "objections": sorted(objections, key=lambda o: o.order_index),
            "active_page": "debate",
        },
    )
