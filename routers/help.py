"""routers/help.py — Centro de ayuda del tenant (/panel/ayuda): FAQ +
tickets de soporte hacia VibeCloud.

Regla 1.1 aplicada: los tickets siempre se crean y se listan filtrados por
el tenant_id del usuario logueado (get_tenant), nunca por uno que mande el
cliente. La bandeja de SuperAdmin (routers/superadmin.py) es la única
vista que cruza tenants, y es explícitamente admin-only.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select

from database.models import Settings, SupportTicket, Tenant, User
from database.session import get_session
from web.compat_templates import CompatTemplates
from web.dependencies import get_settings, get_tenant, require_auth

router = APIRouter(tags=["Ayuda"])


def _templates():
    return CompatTemplates(directory="templates")


def _own_tickets(session: Session, tenant_id: int) -> list[SupportTicket]:
    return session.exec(
        select(SupportTicket)
        .where(SupportTicket.tenant_id == tenant_id)
        .order_by(SupportTicket.created_at.desc())
    ).all()


@router.get("/panel/ayuda", response_class=HTMLResponse)
def help_page(
    request: Request,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
    success: Optional[str] = None,
):
    tenant = session.get(Tenant, tenant_id)
    return _templates().TemplateResponse(
        "panel_ayuda.html",
        {
            "request": request,
            "user": user,
            "settings": settings,
            "tenant": tenant,
            "tickets": _own_tickets(session, tenant_id),
            "success": success,
        },
    )


@router.post("/panel/ayuda/ticket", response_class=HTMLResponse)
def help_create_ticket(
    request: Request,
    subject: str = Form(...),
    message: str = Form(...),
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    subject_clean = subject.strip()
    message_clean = message.strip()
    error = None
    if not subject_clean or not message_clean:
        error = "Completá el asunto y el mensaje antes de enviar."

    if not error:
        ticket = SupportTicket(
            tenant_id=tenant_id,
            user_id=user.id,
            subject=subject_clean,
            message=message_clean,
        )
        session.add(ticket)
        session.commit()

    tenant = session.get(Tenant, tenant_id)
    return _templates().TemplateResponse(
        "panel_ayuda.html",
        {
            "request": request,
            "user": user,
            "settings": settings,
            "tenant": tenant,
            "tickets": _own_tickets(session, tenant_id),
            "error": error,
            "success": None if error else "Tu consulta fue enviada. Te vamos a responder acá mismo.",
        },
    )
