"""routers/cash.py — Libro de Caja"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from database.models import CashMovement, Sale, Settings, User
from database.session import get_session
from services.purchase_service import PurchaseService
from services.settings_service import SettingsService
from web.compat_templates import CompatTemplates
from web.dependencies import get_settings, get_tenant, require_auth

router = APIRouter(tags=["Cash"])


def _templates():
    return CompatTemplates(directory="templates")


@router.get("/cash", response_class=HTMLResponse)
def get_cash_book(
    request: Request,
    date_filter: Optional[str] = Query(None, alias="date"),
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    try:
        target_date = datetime.fromisoformat(date_filter).date() if date_filter else date.today()
    except ValueError:
        target_date = date.today()

    day_start = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    movements = session.exec(
        select(CashMovement)
        .where(
            CashMovement.tenant_id == tenant_id,
            CashMovement.timestamp >= day_start,
            CashMovement.timestamp < day_end,
        )
        .order_by(CashMovement.timestamp.desc())
    ).all()

    from services.cash_service import CashService
    balance_data = CashService.calculate_daily_balance(session, tenant_id, target_date)

    account_sales = session.exec(
        select(Sale).where(
            Sale.tenant_id == tenant_id,
            Sale.timestamp >= day_start,
            Sale.timestamp < day_end,
            Sale.client_id.is_not(None),
            Sale.total_amount > Sale.amount_paid,
        ).order_by(Sale.timestamp.desc())
    ).all()
    
    # Filter for account_sales after last closure of that day (simplified for now as in original)
    def is_close(m):
        return m.movement_type == "cierre" or (m.concept or "").upper().startswith("CIERRE_DE_CAJA")
    last_close_ts = max([m.timestamp for m in movements if is_close(m)], default=None)
    if last_close_ts:
        account_sales = [s for s in account_sales if s.timestamp > last_close_ts]
        
    total_account_receivable = sum(max((s.total_amount or 0.0) - (s.amount_paid or 0.0), 0.0) for s in account_sales)

    return _templates().TemplateResponse(
        "cash_book.html",
        {
            "request": request,
            "active_page": "cash",
            "settings": settings,
            "user": user,
            "movements": movements,
            "total_in": balance_data["total_in"],
            "total_in_cash": balance_data["total_in_cash"],
            "total_in_transfer": balance_data["total_in_transfer"],
            "total_out": abs(balance_data["total_out"]),
            "balance": balance_data["balance"],
            "selected_date": target_date.isoformat(),
            "account_sales": account_sales,
            "total_account_receivable": total_account_receivable,
        },
    )


@router.post("/api/cash/movement")
def create_cash_movement(
    movement_type: str = Form(...),
    amount: float = Form(...),
    concept: str = Form(...),
    session: Session = Depends(get_session),
    user: User = Depends(require_auth),
    tenant_id: int = Depends(get_tenant),
):
    if movement_type not in ["in", "out"]:
        raise HTTPException(400, "Invalid movement type")

    PurchaseService.register_manual_cash_movement(
        session=session,
        tenant_id=tenant_id,
        user_id=user.id,
        amount=amount,
        movement_type=movement_type,
        concept=concept,
        reference_id=None,
        reference_type="manual",
    )
    return RedirectResponse("/cash", status_code=303)
