"""routers/team.py — Equipo: invitar compañeros dentro del mismo tenant.

Regla 1.1 aplicada: tenant_id del nuevo usuario siempre se toma del tenant
logueado (get_tenant), nunca del cliente. username ahora es único POR
TENANT (ver database/models.py::User), así que dos tenants distintos pueden
tener cada uno su propio "admin" sin chocar.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from database.models import Settings, Tenant, User
from database.session import get_session
from routers.admin import _validate_password_strength
from services.auth_service import AuthService
from services.settings_service import SettingsService
from web.compat_templates import CompatTemplates
from web.dependencies import get_settings, get_tenant, require_auth

router = APIRouter(tags=["Equipo"])

ALLOWED_ROLES = ("admin", "cashier", "seller")


def _templates():
    return CompatTemplates(directory="templates")


@router.get("/panel/equipo", response_class=HTMLResponse)
def team_page(
    request: Request,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
    error: Optional[str] = None,
):
    SettingsService.ensure_admin(user)
    members = session.exec(
        select(User)
        .where(User.tenant_id == tenant_id, User.is_deleted == False)
        .order_by(User.id)
    ).all()
    return _templates().TemplateResponse(
        "panel_equipo.html",
        {
            "request": request,
            "user": user,
            "settings": settings,
            "members": members,
            "allowed_roles": ALLOWED_ROLES,
            "error": error,
        },
    )


@router.post("/panel/equipo", response_class=HTMLResponse)
def team_create(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    full_name: Optional[str] = Form(None),
    role: str = Form(...),
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    SettingsService.ensure_admin(user)

    def _render_error(message: str, status_code: int = 400):
        members = session.exec(
            select(User)
            .where(User.tenant_id == tenant_id, User.is_deleted == False)
            .order_by(User.id)
        ).all()
        return _templates().TemplateResponse(
            "panel_equipo.html",
            {
                "request": request,
                "user": user,
                "settings": settings,
                "members": members,
                "allowed_roles": ALLOWED_ROLES,
                "error": message,
            },
            status_code=status_code,
        )

    username_clean = username.strip()
    if not username_clean:
        return _render_error("El usuario es obligatorio")
    if role not in ALLOWED_ROLES:
        return _render_error("Rol inválido")

    try:
        _validate_password_strength(password)
    except HTTPException as exc:
        return _render_error(exc.detail)

    new_user = User(
        username=username_clean,
        password_hash=AuthService.get_password_hash(password),
        role=role,
        full_name=(full_name or "").strip() or None,
        tenant_id=tenant_id,
    )
    session.add(new_user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return _render_error("Ya existe un usuario con ese nombre en tu equipo")

    return _templates().TemplateResponse(
        "panel_equipo.html",
        {
            "request": request,
            "user": user,
            "settings": settings,
            "members": session.exec(
                select(User)
                .where(User.tenant_id == tenant_id, User.is_deleted == False)
                .order_by(User.id)
            ).all(),
            "allowed_roles": ALLOWED_ROLES,
            "success": f"Usuario '{username_clean}' creado",
        },
    )
