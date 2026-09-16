from __future__ import annotations

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from database.models import Settings, Tenant, User
from database.session import get_session
from web.compat_templates import CompatTemplates
from web.dependencies import get_settings, get_tenant, require_auth

router = APIRouter(tags=["Research"])


def _templates():
    return CompatTemplates(directory="templates")


def _require_research_access(tenant: Tenant):
    if not (tenant.has_landing or tenant.has_ecommerce or tenant.has_alexio):
        raise HTTPException(403, "Tu cuenta no tiene acceso al módulo de investigación")


@router.get("/panel/research", response_class=HTMLResponse)
def research_dashboard(
    request: Request,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    from services.research_service import list_projects

    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404)
    _require_research_access(tenant)

    projects = list_projects(session, tenant_id)
    return _templates().TemplateResponse(
        "panel_research.html",
        {
            "request": request,
            "user": user,
            "settings": settings,
            "projects": projects,
            "view": "research",
        },
    )


@router.post("/panel/research/nuevo")
def research_create(
    request: Request,
    project_type: str = Form("physical_product"),
    query_description: str = Form(...),
    reference_url: str = Form(""),
    factory_price: str = Form(""),
    user: User = Depends(require_auth),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    from services.research_service import create_project

    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404)
    _require_research_access(tenant)

    if project_type not in ("physical_product", "digital_service"):
        raise HTTPException(400, "Tipo de proyecto inválido")

    query_description = query_description.strip()
    if not query_description:
        raise HTTPException(400, "Descripción requerida")

    price = None
    if factory_price.strip():
        try:
            price = Decimal(factory_price.strip())
            if price < 0:
                raise HTTPException(400, "El precio no puede ser negativo")
        except InvalidOperation:
            raise HTTPException(400, "Precio inválido")

    project = create_project(
        session=session,
        tenant_id=tenant_id,
        user_id=user.id,
        project_type=project_type,
        query_description=query_description,
        reference_url=reference_url.strip() or None,
        factory_price=price,
    )
    return {"status": "success", "project_id": project.id}


@router.post("/panel/research/{project_id}/buscar")
async def research_run_search(
    project_id: int,
    request: Request,
    user: User = Depends(require_auth),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    from services.research_service import get_project_with_results, run_product_search

    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404)
    _require_research_access(tenant)

    project = get_project_with_results(session, project_id, tenant_id)
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")

    if project.status not in ("draft", "error"):
        raise HTTPException(400, "Este proyecto ya fue investigado")

    try:
        listings = await run_product_search(session, project)
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))

    return {
        "status": "success",
        "listings_count": len(listings),
        "project_id": project.id,
    }


@router.get("/panel/research/{project_id}", response_class=HTMLResponse)
def research_detail(
    project_id: int,
    request: Request,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    from services.research_service import get_project_with_results

    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404)
    _require_research_access(tenant)

    project = get_project_with_results(session, project_id, tenant_id)
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")

    prices = [l.price for l in project.listings if l.price is not None]
    price_range = {"min": min(prices), "max": max(prices)} if prices else None

    margin_pct = None
    if price_range and project.factory_price and project.factory_price > 0:
        avg_price = (price_range["min"] + price_range["max"]) / 2
        margin_pct = round(float((avg_price - project.factory_price) / project.factory_price * 100), 1)

    return _templates().TemplateResponse(
        "panel_research.html",
        {
            "request": request,
            "user": user,
            "settings": settings,
            "project": project,
            "projects": None,
            "price_range": price_range,
            "margin_pct": margin_pct,
            "view": "research_detail",
        },
    )
