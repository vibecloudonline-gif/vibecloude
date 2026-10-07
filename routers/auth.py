"""routers/auth.py — Login / Logout"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from core.config import settings as app_settings
from core.limiter import limiter
from core.security_audit import (
    audit_login_failure,
    audit_login_success,
    audit_logout,
    get_client_ip,
)
from database.models import Settings, Tenant, User
from database.session import get_session
from services.auth_service import AuthService
from web.compat_templates import CompatTemplates
from web.dependencies import _resolve_tenant_from_host, get_settings

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
    #
    # username es unico POR TENANT, no global -- si el host resuelve a un
    # tenant (subdominio o dominio propio) buscamos ahi. Si no resuelve
    # (dominio base sin subdominio, o dev sin BASE_DOMAIN configurada),
    # caemos a la busqueda global de siempre -- ambiguo si ya hay dos
    # tenants con el mismo username, limitacion conocida y aceptada.
    host_tenant_id = _resolve_tenant_from_host(request.headers.get("host"), session)
    if host_tenant_id:
        user = session.exec(
            select(User).where(User.tenant_id == host_tenant_id, User.username == username)
        ).first()
    else:
        user = session.exec(select(User).where(User.username == username)).first()

    client_ip = get_client_ip(request)
    if not user or not user.is_active or user.is_deleted or not AuthService.verify_password(password, user.password_hash):
        audit_login_failure(username, client_ip)
        return _templates().TemplateResponse(
            "login.html", {"request": request, "error": "Credenciales inválidas", "settings": settings}
        )
    request.session.clear()
    request.session["user_id"] = user.id
    audit_login_success(username, user.id, user.tenant_id, client_ip)
    tenant = session.get(Tenant, user.tenant_id) if user.tenant_id else None
    tenant_flags = {
        "erp": tenant.has_erp if tenant else True,
        "ecommerce": tenant.has_ecommerce if tenant else True,
        "landing": tenant.has_landing if tenant else True,
        "courses": tenant.has_courses if tenant else False,
    }
    request.session["tenant_flags"] = tenant_flags
    request.session["tenant_nivel"] = tenant.nivel if tenant else 1
    modules = []
    if tenant_flags.get("ecommerce"):
        modules.append("ecommerce")
    if tenant_flags.get("landing"):
        modules.append("landing")
    if tenant_flags.get("courses"):
        modules.append("courses")
    if not modules:
        modules = ["ecommerce", "landing"]
    request.session["nav_view"] = modules
    if user.role == "superadmin":
        return RedirectResponse("/tenants", status_code=302)
    return RedirectResponse("/", status_code=302)


@router.get("/logout")
def logout(request: Request):
    user_id = request.session.get("user_id")
    audit_logout(user_id or 0, get_client_ip(request))
    request.session.clear()
    return RedirectResponse("/login", status_code=302)
