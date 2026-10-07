"""routers/panel_plan.py — Pantalla "Mi plan" con uso y upgrade."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from database.models import Settings, User
from database.session import get_session
from services.plan_service import PLAN_DEFINITIONS, get_plan_usage
from services.settings_service import SettingsService
from web.compat_templates import CompatTemplates
from web.dependencies import get_settings, get_tenant, require_auth

router = APIRouter(tags=["Plan"])


def _templates():
    return CompatTemplates(directory="templates")


@router.get("/panel/plan")
def panel_plan(
    request: Request,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    SettingsService.ensure_admin(user)
    from database.models import Tenant
    tenant = session.get(Tenant, tenant_id)
    ai_tier = tenant.ai_tier if tenant else "inicial"
    usage = get_plan_usage(session, tenant_id, ai_tier)

    return _templates().TemplateResponse(
        "panel_plan.html",
        {
            "request": request,
            "user": user,
            "settings": settings,
            "active_page": "plan",
            "usage": usage,
            "all_plans": PLAN_DEFINITIONS,
        },
    )
