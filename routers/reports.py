"""routers/reports.py — Reportes Financieros"""
from __future__ import annotations
from datetime import date, datetime
from typing import Optional
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select
from database.models import CashMovement, Sale, SaleItem, Settings, User
from database.session import get_session
from web.compat_templates import CompatTemplates
from web.dependencies import get_settings, get_tenant, require_auth

router = APIRouter(tags=["Reports"])

def _templates():
    return CompatTemplates(directory="templates")

@router.get("/reports/profitability", response_class=HTMLResponse)
def get_profitability_report(request: Request, start_date: Optional[str] = None, end_date: Optional[str] = None, user: User = Depends(require_auth), tenant_id: int = Depends(get_tenant), session: Session = Depends(get_session), settings: Settings = Depends(get_settings)):
    if not start_date: start_date = date.today().replace(day=1).strftime("%Y-%m-%d")
    if not end_date: end_date = date.today().strftime("%Y-%m-%d")
    s_dt = datetime.strptime(start_date, "%Y-%m-%d")
    e_dt = datetime.combine(datetime.strptime(end_date, "%Y-%m-%d"), datetime.max.time())
    from sqlalchemy import select as sa_select
    stmt = sa_select(SaleItem).join(Sale).where(Sale.tenant_id == tenant_id, Sale.timestamp >= s_dt, Sale.timestamp <= e_dt)
    items = session.exec(stmt).all()
    total_revenue, total_cost = 0.0, 0.0
    for item in items:
        qty, price, cost = item.quantity or 0, item.unit_price or 0, item.cost_price_at_sale or 0
        total_revenue += qty * price
        total_cost += qty * cost
    profit = total_revenue - total_cost
    margin = (profit / total_revenue * 100) if total_revenue > 0 else 0
    return _templates().TemplateResponse("reports/profitability.html", {"request": request, "total_revenue": total_revenue, "total_cost": total_cost, "profit": profit, "margin": margin, "start_date": start_date, "end_date": end_date, "user": user, "settings": settings})

from services.cash_service import CashService

@router.get("/reports/cash-flow", response_class=HTMLResponse)
def get_cash_flow_report(request: Request, date_filter: Optional[str] = None, user: User = Depends(require_auth), tenant_id: int = Depends(get_tenant), session: Session = Depends(get_session), settings: Settings = Depends(get_settings)):
    if not date_filter: date_filter = date.today().strftime("%Y-%m-%d")
    try: target_day = datetime.strptime(date_filter, "%Y-%m-%d").date()
    except ValueError:
        target_day = date.today()
        date_filter = target_day.strftime("%Y-%m-%d")
    
    start = datetime.combine(target_day, datetime.min.time()).replace(tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    
    movements = session.exec(select(CashMovement).where(CashMovement.tenant_id == tenant_id, CashMovement.timestamp >= start, CashMovement.timestamp < end).order_by(CashMovement.timestamp.desc())).all()
    
    balance_data = CashService.calculate_daily_balance(session, tenant_id, target_day)
    
    return _templates().TemplateResponse("reports/cash_flow.html", {
        "request": request, 
        "date": date_filter, 
        "movements": movements, 
        "total_in_cash": balance_data["total_in_cash"], 
        "total_in_transfer": balance_data["total_in_transfer"], 
        "total_out": balance_data["total_out"], 
        "balance": balance_data["balance"], 
        "user": user, 
        "settings": settings
    })
