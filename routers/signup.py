"""routers/signup.py — Alta self-service de tenant (Fase 3 del roadmap,
sección 7 de CLAUDE.md/VIBECLOUD_ROADMAP_V2.md).

Cualquier visitante puede crearse una cuenta y elegir qué producto(s)
contrata (ERP, ecommerce, landing con IA, AlexIO) sin intervención manual
del SuperAdmin. Sin billing/pagos -- fuera de alcance, según ya definido.

Regla 1.1 aplicada: el tenant_id del tenant recién creado se resuelve acá
mismo server-side (nunca lo manda el cliente) y se inyecta en la sesión
igual que hace routers/auth.py::login.
"""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from core.config import settings as app_settings
from core.limiter import limiter
from database.models import Settings, Tenant, User
from database.session import get_session
from routers.admin import _validate_password_strength
from services.auth_service import AuthService
from web.compat_templates import CompatTemplates

router = APIRouter(tags=["Signup"])

# Mismo largo/regla que un label DNS valido (RFC 1035): minusculas, numeros,
# guiones, no puede empezar ni terminar en guion.
SUBDOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")

# Subdominios que no se pueden autoasignar porque ya tienen o van a tener un
# significado especial en la plataforma (paneles propios, infraestructura).
RESERVED_SUBDOMAINS = {
    "www", "api", "admin", "app", "mail", "smtp", "ftp", "superadmin",
    "static", "assets", "cdn", "test", "staging", "dev", "panel", "tienda",
    "store", "blog", "help", "soporte", "support", "docs", "status",
}


def _templates():
    return CompatTemplates(directory="templates")


def _normalize_subdomain(raw: str) -> str:
    return (raw or "").strip().lower()


def validate_subdomain_format(subdomain: str) -> Optional[str]:
    """Devuelve None si es válido, o un mensaje de error si no."""
    if not subdomain:
        return "El subdominio es obligatorio"
    if len(subdomain) < 3:
        return "El subdominio debe tener al menos 3 caracteres"
    if not SUBDOMAIN_RE.match(subdomain):
        return "Solo minúsculas, números y guiones -- sin empezar ni terminar en guion"
    if subdomain in RESERVED_SUBDOMAINS:
        return "Ese subdominio está reservado, elegí otro"
    return None


@router.get("/registro", response_class=HTMLResponse)
def signup_page(request: Request):
    return _templates().TemplateResponse("registro.html", {"request": request})


@router.get("/api/registro/subdominio-disponible")
@limiter.limit(app_settings.RATE_LIMIT_PUBLIC)
def check_subdomain_available(
    request: Request,
    subdominio: str,
    session: Session = Depends(get_session),
):
    sub = _normalize_subdomain(subdominio)
    error = validate_subdomain_format(sub)
    if error:
        return {"subdomain": sub, "available": False, "reason": error}

    existing = session.exec(select(Tenant).where(Tenant.subdomain == sub)).first()
    if existing:
        return {"subdomain": sub, "available": False, "reason": "Ese subdominio ya está en uso"}

    return {"subdomain": sub, "available": True, "reason": None}


@router.post("/registro")
@limiter.limit(app_settings.RATE_LIMIT_LOGIN)
def signup_submit(
    request: Request,
    empresa: str = Form(...),
    subdominio: str = Form(...),
    admin_username: str = Form(...),
    admin_password: str = Form(...),
    admin_full_name: Optional[str] = Form(None),
    has_erp: bool = Form(False),
    has_ecommerce: bool = Form(False),
    has_landing: bool = Form(False),
    has_alexio: bool = Form(False),
    session: Session = Depends(get_session),
):
    empresa_clean = empresa.strip()
    if not empresa_clean:
        return _templates().TemplateResponse(
            "registro.html", {"request": request, "error": "El nombre de la empresa es obligatorio"}, status_code=400
        )

    sub = _normalize_subdomain(subdominio)
    sub_error = validate_subdomain_format(sub)
    if sub_error:
        return _templates().TemplateResponse("registro.html", {"request": request, "error": sub_error}, status_code=400)

    if session.exec(select(Tenant).where(Tenant.subdomain == sub)).first():
        return _templates().TemplateResponse(
            "registro.html", {"request": request, "error": "Ese subdominio ya está en uso"}, status_code=400
        )

    if not (has_erp or has_ecommerce or has_landing or has_alexio):
        return _templates().TemplateResponse(
            "registro.html", {"request": request, "error": "Elegí al menos un producto"}, status_code=400
        )

    admin_username_clean = admin_username.strip()
    if not admin_username_clean:
        return _templates().TemplateResponse(
            "registro.html", {"request": request, "error": "El usuario admin es obligatorio"}, status_code=400
        )

    try:
        _validate_password_strength(admin_password)
    except HTTPException as exc:
        return _templates().TemplateResponse(
            "registro.html", {"request": request, "error": exc.detail}, status_code=400
        )

    tenant = Tenant(
        name=empresa_clean,
        subdomain=sub,
        has_erp=has_erp,
        has_ecommerce=has_ecommerce,
        has_landing=has_landing,
        has_alexio=has_alexio,
    )
    session.add(tenant)
    session.commit()
    session.refresh(tenant)

    settings_obj = Settings(tenant_id=tenant.id, company_name=empresa_clean, logo_url="/static/images/logo.png")
    session.add(settings_obj)

    admin_user = User(
        username=admin_username_clean,
        password_hash=AuthService.get_password_hash(admin_password),
        role="admin",
        full_name=(admin_full_name or "").strip() or None,
        tenant_id=tenant.id,
    )
    session.add(admin_user)

    try:
        session.commit()
    except Exception:
        session.rollback()
        # El tenant ya quedo creado en el commit anterior -- se limpia para no
        # dejar un tenant huérfano sin admin si el username estaba duplicado
        # (User.username es unico globalmente, no por tenant).
        session.delete(tenant)
        session.commit()
        return _templates().TemplateResponse(
            "registro.html", {"request": request, "error": "Ese nombre de usuario ya está en uso"}, status_code=400
        )

    session.refresh(admin_user)

    request.session["user_id"] = admin_user.id
    tenant_flags = {"erp": has_erp, "ecommerce": has_ecommerce, "landing": has_landing}
    request.session["tenant_flags"] = tenant_flags
    request.session["nav_view"] = [k for k, v in tenant_flags.items() if v]

    return RedirectResponse("/", status_code=302)
