from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional

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
    accept = request.headers.get("accept", "")
    is_ajax = "application/json" in accept or request.headers.get("x-requested-with") == "XMLHttpRequest"
    if "text/html" in accept and not is_ajax:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(f"/panel/research/{project.id}", status_code=303)
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

    if project.status == "researching":
        raise HTTPException(400, "Ya hay una búsqueda en progreso para este proyecto")

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


@router.post("/panel/research/{project_id}/competencia")
async def research_add_competitor(
    project_id: int,
    request: Request,
    user: User = Depends(require_auth),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    from services.competitor_service import add_competitor, run_competitor_analysis
    from services.research_service import get_project_with_results

    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404)
    _require_research_access(tenant)

    project = get_project_with_results(session, project_id, tenant_id)
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
        url = str(body.get("url", "")).strip()
        notes = body.get("notes")
    else:
        form = await request.form()
        url = str(form.get("url", "")).strip()
        notes = form.get("notes")

    if not url:
        raise HTTPException(400, "URL del competidor requerida")

    try:
        competitor = add_competitor(
            session=session,
            project_id=project_id,
            tenant_id=tenant_id,
            url=url,
            notes=str(notes).strip() if notes else None,
        )
    except ValueError as val_err:
        raise HTTPException(400, str(val_err))

    # Ejecutar análisis en cascada para este competidor
    try:
        await run_competitor_analysis(session, project)
        session.refresh(competitor)
    except Exception as exc:
        # No bloquear la creación si la IA falla; quedará pendiente
        pass

    return {
        "status": "success",
        "competitor": {
            "id": competitor.id,
            "url": competitor.url,
            "value_proposition": competitor.value_proposition,
            "price_info": competitor.price_info,
            "guarantees": competitor.guarantees,
            "objections_addressed": competitor.objections_addressed,
            "user_confirmed": competitor.user_confirmed,
        },
    }


@router.get("/panel/research/{project_id}/competencia")
def research_list_competitors(
    project_id: int,
    request: Request,
    user: User = Depends(require_auth),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    from services.competitor_service import list_competitors

    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404)
    _require_research_access(tenant)

    competitors = list_competitors(session, project_id, tenant_id)
    return {
        "status": "success",
        "competitors": [
            {
                "id": c.id,
                "url": c.url,
                "value_proposition": c.value_proposition,
                "price_info": c.price_info,
                "guarantees": c.guarantees,
                "objections_addressed": c.objections_addressed,
                "user_confirmed": c.user_confirmed,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in competitors
        ],
    }


@router.delete("/panel/research/{project_id}/competencia/{competitor_id}")
def research_delete_competitor(
    project_id: int,
    competitor_id: int,
    request: Request,
    user: User = Depends(require_auth),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    from services.competitor_service import remove_competitor

    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404)
    _require_research_access(tenant)

    success = remove_competitor(session, competitor_id, tenant_id)
    if not success:
        raise HTTPException(404, "Competidor no encontrado o no pertenece al tenant")

    return {"status": "success", "message": "Competidor eliminado correctamente"}


@router.post("/panel/research/{project_id}/competencia/{competitor_id}/confirmar")
def research_confirm_competitor(
    project_id: int,
    competitor_id: int,
    request: Request,
    user: User = Depends(require_auth),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    from services.competitor_service import confirm_competitor

    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404)
    _require_research_access(tenant)

    comp = confirm_competitor(session, competitor_id, tenant_id)
    if not comp:
        raise HTTPException(404, "Competidor no encontrado o no pertenece al tenant")

    return {
        "status": "success",
        "competitor": {
            "id": comp.id,
            "url": comp.url,
            "user_confirmed": comp.user_confirmed,
        },
    }


# ---------------------------------------------------------------------------
# TIMESFM — FORECAST DE MERCADO
# ---------------------------------------------------------------------------

@router.post("/panel/research/{project_id}/forecast")
async def research_generate_forecast(
    project_id: int,
    request: Request,
    horizon_days: int = Form(default=30),
    user: User = Depends(require_auth),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    """Genera (o regenera) el forecast de precio/demanda con TimesFM/Gemini."""
    import json as _json
    from sqlmodel import select
    from database.models import ResearchForecast
    from services.research_service import get_project_with_results
    from services.timesfm_provider import generate_market_forecast

    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404)
    _require_research_access(tenant)

    project = get_project_with_results(session, project_id, tenant_id)
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")
    if not project.listings:
        raise HTTPException(400, "El proyecto no tiene listings. Inicia la búsqueda de mercado primero.")

    prices = [float(l.price) for l in project.listings if l.price is not None]
    if not prices:
        raise HTTPException(400, "No hay precios disponibles en los listings para generar el forecast.")

    if horizon_days not in (30, 90):
        horizon_days = 30

    # Limpiar forecast previo con mismo horizonte
    existing = session.exec(
        select(ResearchForecast).where(
            ResearchForecast.project_id == project_id,
            ResearchForecast.horizon_days == horizon_days,
        )
    ).first()
    if existing:
        session.delete(existing)
        session.flush()

    result = await generate_market_forecast(project.query_description, prices, horizon_days)

    forecast_row = ResearchForecast(
        project_id=project_id,
        horizon_days=horizon_days,
        price_series=_json.dumps(result.price_series),
        forecast_series=_json.dumps(result.forecast_series),
        confidence_low=_json.dumps(result.confidence_low),
        confidence_high=_json.dumps(result.confidence_high),
        trend_direction=result.trend_direction,
        launch_window=result.launch_window,
        recommendation=result.recommendation,
        provider=result.provider,
    )
    session.add(forecast_row)
    session.commit()
    session.refresh(forecast_row)

    return {
        "status": "success",
        "forecast_id": forecast_row.id,
        "trend_direction": result.trend_direction,
        "launch_window": result.launch_window,
        "provider": result.provider,
    }


def _render_forecast_view(
    request: Request,
    project_id: int | None,
    user: User,
    settings: Settings,
    session: Session,
    tenant_id: int,
):
    """Renderiza el panel de visualización del forecast Google TimesFM."""
    import json as _json
    from sqlmodel import select
    from database.models import ResearchForecast, ResearchProject
    from services.research_service import get_project_with_results, list_projects

    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404)
    _require_research_access(tenant)

    all_projects = list_projects(session, tenant_id)
    project = None
    if project_id is not None:
        project = get_project_with_results(session, project_id, tenant_id)
    elif all_projects:
        for p in all_projects:
            if p.listings:
                project = get_project_with_results(session, p.id, tenant_id)
                break
        if not project:
            project = get_project_with_results(session, all_projects[0].id, tenant_id)

    forecast_30 = None
    forecast_90 = None
    if project:
        forecast_30 = session.exec(
            select(ResearchForecast).where(
                ResearchForecast.project_id == project.id,
                ResearchForecast.horizon_days == 30,
            )
        ).first()
        forecast_90 = session.exec(
            select(ResearchForecast).where(
                ResearchForecast.project_id == project.id,
                ResearchForecast.horizon_days == 90,
            )
        ).first()

    def parse_forecast(fc):
        if not fc:
            return None
        return {
            "id": fc.id,
            "horizon_days": fc.horizon_days,
            "price_series": _json.loads(fc.price_series or "[]"),
            "forecast_series": _json.loads(fc.forecast_series or "[]"),
            "confidence_low": _json.loads(fc.confidence_low or "[]"),
            "confidence_high": _json.loads(fc.confidence_high or "[]"),
            "trend_direction": fc.trend_direction,
            "launch_window": fc.launch_window,
            "recommendation": fc.recommendation,
            "provider": fc.provider,
        }

    return _templates().TemplateResponse("panel_timesfm.html", {
        "request": request,
        "user": user,
        "settings": settings,
        "project": project,
        "all_projects": all_projects,
        "forecast_30": parse_forecast(forecast_30),
        "forecast_90": parse_forecast(forecast_90),
        "active_page": "forecast",
    })


@router.get("/panel/forecast", response_class=HTMLResponse)
def research_forecast_index(
    request: Request,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    return _render_forecast_view(request, None, user, settings, session, tenant_id)


@router.get("/panel/forecast/{project_id}", response_class=HTMLResponse)
def research_forecast_detail(
    project_id: int,
    request: Request,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    return _render_forecast_view(request, project_id, user, settings, session, tenant_id)


@router.post("/panel/forecast/instant")
async def research_instant_forecast(
    request: Request,
    query: str = Form(...),
    horizon_days: int = Form(default=30),
    user: User = Depends(require_auth),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    """Crea un proyecto y corre de inmediato el forecast TimesFM con IA."""
    import json as _json
    from services.research_service import create_project, run_product_search
    from services.timesfm_provider import generate_market_forecast
    from database.models import ResearchForecast

    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404)
    _require_research_access(tenant)

    clean_query = query.strip() if query else ""
    if not clean_query:
        raise HTTPException(400, "Ingresa un producto o nicho para predecir")

    # 1. Crear proyecto automáticamente
    project = create_project(
        session=session,
        tenant_id=tenant_id,
        user_id=user.id,
        project_type="physical_product",
        query_description=clean_query,
    )

    # 2. Obtener listings de mercado
    try:
        listings = await run_product_search(session, project)
    except Exception as exc:
        raise HTTPException(500, f"Error al analizar mercado: {exc}")

    prices = [float(l.price) for l in listings if l.price is not None]
    if not prices:
        prices = [29.99, 34.50, 24.90, 39.00]

    # 3. Generar forecast
    result = await generate_market_forecast(project.query_description, prices, horizon_days)
    forecast_row = ResearchForecast(
        project_id=project.id,
        horizon_days=horizon_days,
        price_series=_json.dumps(result.price_series),
        forecast_series=_json.dumps(result.forecast_series),
        confidence_low=_json.dumps(result.confidence_low),
        confidence_high=_json.dumps(result.confidence_high),
        trend_direction=result.trend_direction,
        launch_window=result.launch_window,
        recommendation=result.recommendation,
        provider=result.provider,
    )
    session.add(forecast_row)
    session.commit()

    return {"status": "success", "project_id": project.id, "forecast_id": forecast_row.id}
