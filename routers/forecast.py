from __future__ import annotations

import json
import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from database.models import (
    ResearchForecast,
    ResearchListing,
    ResearchProject,
    Settings,
    Tenant,
    User,
)
from database.session import get_session
from services.timesfm_provider import TimesFMProvider
from web.compat_templates import CompatTemplates
from web.dependencies import get_settings, get_tenant, require_auth

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Forecast"])


def _templates():
    return CompatTemplates(directory="templates")


@router.get("/panel/forecast", response_class=HTMLResponse)
def forecast_dashboard(
    request: Request,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    projects = session.exec(
        select(ResearchProject)
        .where(ResearchProject.tenant_id == tenant_id)
        .where(ResearchProject.status == "completed")
        .order_by(ResearchProject.created_at.desc())
    ).all()

    return _templates().TemplateResponse(
        "panel_timesfm.html",
        {
            "request": request,
            "user": user,
            "settings": settings,
            "active_page": "forecast",
            "projects": projects,
            "forecast": None,
            "project": None,
        },
    )


@router.get("/panel/forecast/{project_id}", response_class=HTMLResponse)
async def forecast_detail(
    request: Request,
    project_id: int,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    project = session.get(ResearchProject, project_id)
    if not project or project.tenant_id != tenant_id:
        raise HTTPException(404, "Proyecto no encontrado")

    forecast = session.exec(
        select(ResearchForecast)
        .where(ResearchForecast.project_id == project_id)
        .order_by(ResearchForecast.created_at.desc())
    ).first()

    if not forecast:
        prices = _extract_prices(session, project_id)
        if not prices:
            return RedirectResponse(f"/panel/research/{project_id}", status_code=303)

        provider = TimesFMProvider()
        result = await provider.generate_forecast(
            prices, project.query_description, horizon_days=30
        )
        forecast = _save_forecast(session, project_id, result)

    price_series = json.loads(forecast.price_series_json or "[]")
    forecast_series = json.loads(forecast.forecast_series_json or "[]")
    conf_low = json.loads(forecast.confidence_low_json or "[]")
    conf_high = json.loads(forecast.confidence_high_json or "[]")

    return _templates().TemplateResponse(
        "panel_timesfm.html",
        {
            "request": request,
            "user": user,
            "settings": settings,
            "active_page": "forecast",
            "project": project,
            "forecast": forecast,
            "price_series_json": json.dumps(price_series),
            "forecast_series_json": json.dumps(forecast_series),
            "confidence_low_json": json.dumps(conf_low),
            "confidence_high_json": json.dumps(conf_high),
            "price_count": len(price_series),
        },
    )


@router.post("/panel/research/{project_id}/forecast")
async def generate_forecast(
    request: Request,
    project_id: int,
    user: User = Depends(require_auth),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
    horizon: int = Form(default=30),
):
    project = session.get(ResearchProject, project_id)
    if not project or project.tenant_id != tenant_id:
        raise HTTPException(404, "Proyecto no encontrado")

    prices = _extract_prices(session, project_id)
    if not prices:
        raise HTTPException(400, "No hay datos de precio para generar forecast")

    provider = TimesFMProvider()
    result = await provider.generate_forecast(
        prices, project.query_description, horizon_days=horizon
    )
    _save_forecast(session, project_id, result)

    return RedirectResponse(f"/panel/forecast/{project_id}", status_code=303)


@router.post("/panel/forecast/instant", response_class=HTMLResponse)
async def instant_forecast(
    request: Request,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
    query: str = Form(...),
    horizon: int = Form(default=30),
):
    demo_prices = [
        100.0, 102.5, 99.8, 105.0, 103.2, 107.1, 104.5,
        108.0, 106.3, 110.2, 109.0, 112.5, 111.8, 115.0,
        113.2, 116.5, 114.8, 118.0, 117.2, 120.0,
    ]

    provider = TimesFMProvider()
    result = await provider.generate_forecast(demo_prices, query, horizon_days=horizon)

    forecast_obj = ResearchForecast(
        project_id=0,
        horizon_days=result["horizon_days"],
        price_series_json=json.dumps(result["price_series"]),
        forecast_series_json=json.dumps(result["forecast_series"]),
        confidence_low_json=json.dumps(result["confidence_low"]),
        confidence_high_json=json.dumps(result["confidence_high"]),
        trend_direction=result["trend_direction"],
        launch_window=result.get("launch_window"),
        summary=result.get("summary"),
    )

    class FakeProject:
        id = 0
        query_description = query

    return _templates().TemplateResponse(
        "panel_timesfm.html",
        {
            "request": request,
            "user": user,
            "settings": settings,
            "active_page": "forecast",
            "project": FakeProject(),
            "forecast": forecast_obj,
            "price_series_json": json.dumps(result["price_series"]),
            "forecast_series_json": json.dumps(result["forecast_series"]),
            "confidence_low_json": json.dumps(result["confidence_low"]),
            "confidence_high_json": json.dumps(result["confidence_high"]),
            "price_count": len(result["price_series"]),
        },
    )


def _extract_prices(session: Session, project_id: int) -> list[float]:
    listings = session.exec(
        select(ResearchListing)
        .where(ResearchListing.project_id == project_id)
        .where(ResearchListing.price.isnot(None))
    ).all()

    prices = [float(l.price) for l in listings if l.price and l.price > 0]
    if not prices:
        return []
    return sorted(prices)


def _save_forecast(
    session: Session, project_id: int, result: dict
) -> ResearchForecast:
    forecast = ResearchForecast(
        project_id=project_id,
        horizon_days=result["horizon_days"],
        price_series_json=json.dumps(result["price_series"]),
        forecast_series_json=json.dumps(result["forecast_series"]),
        confidence_low_json=json.dumps(result["confidence_low"]),
        confidence_high_json=json.dumps(result["confidence_high"]),
        trend_direction=result["trend_direction"],
        launch_window=result.get("launch_window"),
        summary=result.get("summary"),
    )
    session.add(forecast)
    session.commit()
    session.refresh(forecast)
    return forecast
