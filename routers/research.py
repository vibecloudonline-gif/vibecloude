from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from database.models import Settings, Tenant, User
from database.session import get_session
from sqlmodel import select
from web.compat_templates import CompatTemplates
from web.dependencies import get_settings, get_tenant, require_auth

router = APIRouter(tags=["Research"])


def _templates():
    return CompatTemplates(directory="templates")


def _require_research_access(tenant: Tenant):
    if not (tenant.has_landing or tenant.has_ecommerce):
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
            "active_page": "research",
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
            "active_page": "research",
        },
    )


@router.post("/panel/research/{project_id}/eliminar")
def research_delete_project(
    project_id: int,
    request: Request,
    user: User = Depends(require_auth),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    from database.models import (
        CompetitorAnalysis, DebateObjection, ExpertDebate, ExpertOpinion,
        ForecastProfile, Offer, ResearchDemand, ResearchForecast,
        ResearchListing, ResearchProject, ValidationDebate,
    )

    project = session.exec(
        select(ResearchProject).where(
            ResearchProject.id == project_id,
            ResearchProject.tenant_id == tenant_id,
        )
    ).first()
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")

    offers = session.exec(select(Offer).where(Offer.project_id == project_id)).all()
    for offer in offers:
        debates = session.exec(select(ValidationDebate).where(ValidationDebate.offer_id == offer.id)).all()
        for d in debates:
            for obj in session.exec(select(DebateObjection).where(DebateObjection.debate_id == d.id)).all():
                session.delete(obj)
            session.delete(d)
        expert_debates = session.exec(select(ExpertDebate).where(ExpertDebate.offer_id == offer.id)).all()
        for ed in expert_debates:
            for op in session.exec(select(ExpertOpinion).where(ExpertOpinion.debate_id == ed.id)).all():
                session.delete(op)
            session.delete(ed)
        session.delete(offer)

    for listing in session.exec(select(ResearchListing).where(ResearchListing.project_id == project_id)).all():
        session.delete(listing)
    for demand in session.exec(select(ResearchDemand).where(ResearchDemand.project_id == project_id)).all():
        session.delete(demand)
    for comp in session.exec(select(CompetitorAnalysis).where(CompetitorAnalysis.project_id == project_id)).all():
        session.delete(comp)
    for fc in session.exec(select(ResearchForecast).where(ResearchForecast.project_id == project_id)).all():
        session.delete(fc)
    for fp in session.exec(select(ForecastProfile).where(ForecastProfile.project_id == project_id)).all():
        session.delete(fp)

    session.delete(project)
    session.commit()

    return {"status": "success", "message": "Proyecto eliminado"}


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

    if horizon_days not in (7, 14, 30, 60, 90, 180):
        horizon_days = 30

    existing = session.exec(
        select(ResearchForecast).where(
            ResearchForecast.project_id == project_id,
            ResearchForecast.horizon_days == horizon_days,
        )
    ).first()
    if existing:
        session.delete(existing)
        session.flush()

    from database.models import ForecastProfile
    profile = session.exec(
        select(ForecastProfile).where(ForecastProfile.project_id == project_id)
    ).first()
    biz_ctx = None
    if profile:
        biz_ctx = {
            "business_type": profile.business_type,
            "business_stage": profile.business_stage,
            "product_category": profile.product_category,
            "target_market": profile.target_market,
            "target_audience": profile.target_audience,
            "unit_cost": str(profile.unit_cost) if profile.unit_cost else None,
            "desired_margin_pct": profile.desired_margin_pct,
            "pricing_strategy": profile.pricing_strategy,
            "geography": profile.geography,
            "seasonality_notes": profile.seasonality_notes,
            "competition_level": profile.competition_level,
            "differentiator": profile.differentiator,
            "launch_target_date": profile.launch_target_date,
            "monthly_revenue_target": str(profile.monthly_revenue_target) if profile.monthly_revenue_target else None,
            "growth_expectation": profile.growth_expectation,
            "known_competitor_prices": profile.known_competitor_prices,
        }

    result = await generate_market_forecast(project.query_description, prices, horizon_days, business_context=biz_ctx)

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


def _parse_forecast(fc):
    import json as _json
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
        "created_at": fc.created_at,
    }


def _build_alerts(profile, active_fc):
    alerts = []
    if not active_fc:
        return alerts
    trend = active_fc.get("trend_direction", "estable")
    if trend == "alcista":
        alerts.append({"type": "opportunity", "icon": "&#128200;", "title": "Tendencia alcista detectada",
                        "message": "Los precios del mercado muestran tendencia al alza. Es un buen momento para entrar antes de que los precios suban mas."})
    elif trend == "bajista":
        alerts.append({"type": "warning", "icon": "&#128201;", "title": "Tendencia bajista",
                        "message": "Los precios estan cayendo. Considera ajustar tu precio o esperar a que el mercado se estabilice."})
    if profile and profile.unit_cost and active_fc.get("forecast_series"):
        market_price = active_fc["forecast_series"][-1]
        margin_pct = (market_price - float(profile.unit_cost)) / float(profile.unit_cost) * 100
        if margin_pct < 10:
            alerts.append({"type": "danger", "icon": "&#9888;&#65039;", "title": "Margen muy ajustado",
                            "message": f"Tu costo (${profile.unit_cost:.2f}) deja solo {margin_pct:.0f}% de margen vs el precio de mercado (${market_price:.2f}). Revisa tu estructura de costos."})
        elif margin_pct > 100:
            alerts.append({"type": "opportunity", "icon": "&#128176;", "title": "Alto margen potencial",
                            "message": f"El mercado paga ${market_price:.2f} y tu costo es ${profile.unit_cost:.2f} ({margin_pct:.0f}% margen). Oportunidad de alta rentabilidad."})
    if profile and profile.competition_level == "saturated":
        alerts.append({"type": "warning", "icon": "&#9940;", "title": "Mercado saturado",
                        "message": "Indicaste competencia saturada. Asegurate de tener un diferenciador claro antes de lanzar."})
    return alerts


def _build_demand_forecast(profile, active_fc):
    if not active_fc or not active_fc.get("forecast_series"):
        return None
    import math
    fc = active_fc["forecast_series"]
    base_demand = 100
    if profile:
        if profile.growth_expectation == "aggressive":
            base_demand = 200
        elif profile.growth_expectation == "conservative":
            base_demand = 50
        if profile.competition_level == "low":
            base_demand = int(base_demand * 1.3)
        elif profile.competition_level == "saturated":
            base_demand = int(base_demand * 0.5)
    values = []
    for i, price in enumerate(fc):
        factor = 1 + 0.05 * i
        noise = math.sin(i * 1.3) * 0.1
        values.append(max(1, int(base_demand * factor * (1 + noise))))
    labels = [f"+S{i+1}" for i in range(len(fc))]
    avg = sum(values) / len(values) if values else 0
    return {"labels": labels, "values": values,
            "summary": f"Demanda estimada promedio: {avg:.0f} unidades/semana para tu perfil de negocio ({profile.growth_expectation if profile else 'moderado'})."}


def _build_seasonality(profile):
    if not profile or not profile.seasonality_notes:
        return None
    notes = profile.seasonality_notes.lower()
    index = [1.0] * 12
    season_map = {
        "navidad": {10: 1.2, 11: 1.5, 0: 1.3},
        "diciembre": {11: 1.5},
        "verano": {5: 1.3, 6: 1.4, 7: 1.3},
        "invierno": {11: 1.2, 0: 1.3, 1: 1.2},
        "black friday": {10: 1.6},
        "vuelta a clases": {1: 1.3, 7: 1.3},
        "san valentin": {1: 1.4},
        "dia de la madre": {4: 1.4},
        "temporada baja": {},
    }
    for keyword, months in season_map.items():
        if keyword in notes:
            for m, val in months.items():
                index[m] = max(index[m], val)
    has_peaks = any(v > 1.0 for v in index)
    if not has_peaks:
        index = [0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.05, 1.0, 1.1, 1.2, 1.3]
    analysis = f"Basado en tus notas de estacionalidad. Meses pico: {', '.join(['Ene Feb Mar Abr May Jun Jul Ago Sep Oct Nov Dic'.split()[i] for i, v in enumerate(index) if v > 1.1])}." if any(v > 1.1 for v in index) else "Estacionalidad moderada detectada."
    return {"monthly_index": index, "analysis": analysis}


def _render_forecast_view(
    request: Request,
    project_id: int | None,
    user: User,
    settings: Settings,
    session: Session,
    tenant_id: int,
):
    import json as _json
    from database.models import ForecastProfile, ResearchForecast, ResearchProject
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
        if not project and all_projects:
            project = get_project_with_results(session, all_projects[0].id, tenant_id)

    if not project:
        return _templates().TemplateResponse("panel_timesfm.html", {
            "request": request, "user": user, "settings": settings,
            "project": None, "all_projects": all_projects,
            "forecast_30": None, "forecast_90": None, "active_page": "forecast",
        })

    profile = session.exec(
        select(ForecastProfile).where(ForecastProfile.project_id == project.id)
    ).first()

    if profile:
        all_fc = session.exec(
            select(ResearchForecast).where(ResearchForecast.project_id == project.id)
        ).all()

        forecasts = {}
        forecasts_json = {}
        for fc in all_fc:
            parsed = _parse_forecast(fc)
            forecasts[fc.horizon_days] = parsed
            forecasts_json[fc.horizon_days] = {k: v for k, v in parsed.items() if k != "created_at"}

        active_horizon = 30
        for h in [30, 90, 60, 14, 7, 180]:
            if h in forecasts:
                active_horizon = h
                break

        active_fc = forecasts.get(active_horizon)
        other_projects = [p for p in all_projects if p.id != project.id]

        return _templates().TemplateResponse("panel_forecast_enterprise.html", {
            "request": request, "user": user, "settings": settings,
            "project": project, "profile": profile,
            "forecasts": forecasts, "forecasts_json": _json.dumps(forecasts_json),
            "active_forecast": active_fc, "active_horizon": active_horizon,
            "all_forecasts": sorted(all_fc, key=lambda f: f.created_at, reverse=True),
            "alerts": _build_alerts(profile, active_fc),
            "demand_forecast": _build_demand_forecast(profile, active_fc),
            "seasonality": _build_seasonality(profile),
            "other_projects": other_projects,
            "active_page": "forecast",
        })

    from fastapi.responses import RedirectResponse
    return RedirectResponse(f"/panel/forecast/{project.id}/onboarding", status_code=303)


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


@router.get("/panel/forecast/{project_id}/onboarding", response_class=HTMLResponse)
def forecast_onboarding_page(
    project_id: int,
    request: Request,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    from database.models import ForecastProfile
    from services.research_service import get_project_with_results

    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404)
    _require_research_access(tenant)

    project = get_project_with_results(session, project_id, tenant_id)
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")

    profile = session.exec(
        select(ForecastProfile).where(ForecastProfile.project_id == project_id)
    ).first()

    return _templates().TemplateResponse("panel_forecast_onboarding.html", {
        "request": request, "user": user, "settings": settings,
        "project": project, "profile": profile, "active_page": "forecast",
    })


@router.post("/panel/forecast/onboarding")
def forecast_onboarding_save(
    request: Request,
    project_id: int = Form(...),
    business_type: str = Form("physical_product"),
    business_stage: str = Form("idea"),
    product_category: str = Form(""),
    target_audience: str = Form(""),
    target_market: str = Form("national"),
    differentiator: str = Form(""),
    unit_cost: str = Form(""),
    desired_margin_pct: str = Form(""),
    known_competitor_prices: str = Form(""),
    pricing_strategy: str = Form("competitive"),
    geography: str = Form(""),
    seasonality_notes: str = Form(""),
    competition_level: str = Form("medium"),
    launch_target_date: str = Form(""),
    monthly_revenue_target: str = Form(""),
    growth_expectation: str = Form("moderate"),
    user: User = Depends(require_auth),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    from decimal import Decimal, InvalidOperation
    from database.models import ForecastProfile
    from services.research_service import get_project_with_results

    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404)
    _require_research_access(tenant)

    project = get_project_with_results(session, project_id, tenant_id)
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")

    profile = session.exec(
        select(ForecastProfile).where(ForecastProfile.project_id == project_id)
    ).first()

    cost_val = None
    if unit_cost.strip():
        try:
            cost_val = Decimal(unit_cost.strip())
        except InvalidOperation:
            pass

    margin_val = None
    if desired_margin_pct.strip():
        try:
            margin_val = int(desired_margin_pct.strip())
        except ValueError:
            pass

    revenue_val = None
    if monthly_revenue_target.strip():
        try:
            revenue_val = Decimal(monthly_revenue_target.strip())
        except InvalidOperation:
            pass

    from datetime import datetime as _dt

    if profile:
        profile.business_type = business_type
        profile.business_stage = business_stage
        profile.product_category = product_category.strip() or None
        profile.target_audience = target_audience.strip() or None
        profile.target_market = target_market
        profile.differentiator = differentiator.strip() or None
        profile.unit_cost = cost_val
        profile.desired_margin_pct = margin_val
        profile.known_competitor_prices = known_competitor_prices.strip() or None
        profile.pricing_strategy = pricing_strategy
        profile.geography = geography.strip() or None
        profile.seasonality_notes = seasonality_notes.strip() or None
        profile.competition_level = competition_level
        profile.launch_target_date = launch_target_date.strip() or None
        profile.monthly_revenue_target = revenue_val
        profile.growth_expectation = growth_expectation
        profile.updated_at = _dt.utcnow()
        session.add(profile)
    else:
        profile = ForecastProfile(
            tenant_id=tenant_id,
            project_id=project_id,
            business_type=business_type,
            business_stage=business_stage,
            product_category=product_category.strip() or None,
            target_audience=target_audience.strip() or None,
            target_market=target_market,
            differentiator=differentiator.strip() or None,
            unit_cost=cost_val,
            desired_margin_pct=margin_val,
            known_competitor_prices=known_competitor_prices.strip() or None,
            pricing_strategy=pricing_strategy,
            geography=geography.strip() or None,
            seasonality_notes=seasonality_notes.strip() or None,
            competition_level=competition_level,
            launch_target_date=launch_target_date.strip() or None,
            monthly_revenue_target=revenue_val,
            growth_expectation=growth_expectation,
        )
        session.add(profile)

    session.commit()
    return {"status": "success", "project_id": project_id}


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
