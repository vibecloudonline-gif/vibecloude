"""routers/auth.py — Login / Logout"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from core.config import settings as app_settings
from core.limiter import limiter
from database.models import Settings, Tenant, User
from database.session import get_session
from services.auth_service import AuthService
from web.compat_templates import CompatTemplates
from web.dependencies import get_settings

router = APIRouter(tags=["Auth"])

def _templates():
    return CompatTemplates(directory="templates")


@router.get("/login", response_class=HTMLResponse)
@router.head("/login")
def login_page(request: Request, settings: Settings = Depends(get_settings)):
    return _templates().TemplateResponse("login.html", {"request": request, "settings": settings})


@router.post("/login")
@limiter.limit(app_settings.RATE_LIMIT_LOGIN)
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    # El usuario admin/superadmin ya se crea y se sincroniza contra ADMIN_PASSWORD /
    # SUPERADMIN_PASSWORD en cada arranque (ver AuthService.create_default_user_and_settings,
    # llamado desde core/startup.py). No hace falta ni es seguro tener acá un segundo camino
    # de login que compare la password en texto plano contra una env var.
    user = session.exec(select(User).where(User.username == username)).first()

    if not user or not user.is_active or user.is_deleted or not AuthService.verify_password(password, user.password_hash):
        return _templates().TemplateResponse(
            "login.html", {"request": request, "error": "Credenciales inválidas", "settings": settings}
        )
    request.session["user_id"] = user.id
    tenant = session.get(Tenant, user.tenant_id) if user.tenant_id else None
    tenant_flags = {
        "erp": tenant.has_erp if tenant else True,
        "ecommerce": tenant.has_ecommerce if tenant else True,
        "landing": tenant.has_landing if tenant else True,
    }
    request.session["tenant_flags"] = tenant_flags
    # Vista inicial: todo lo que tiene contratado, se puede achicar despues con el switcher.
    request.session["nav_view"] = [k for k, v in tenant_flags.items() if v]
    if user.role == "superadmin":
        return RedirectResponse("/tenants", status_code=302)
    return RedirectResponse("/", status_code=302)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)
