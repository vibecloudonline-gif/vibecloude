"""routers/panel_domains.py — Panel self-service de dominios para el propio
tenant (no confundir con routers/admin.py, que es la versión SuperAdmin que
opera sobre cualquier tenant por path param).

Regla 1.1 aplicada: el tenant_id siempre sale de get_tenant (el tenant
logueado), nunca de un parámetro que mande el cliente. Igual que en
routers/signup.py, este panel solo puede *solicitar* la compra de un
dominio (status="purchase_requested") -- nunca llama a
GoDaddyClient.register_domain, eso sigue siendo exclusivo de
routers/admin.py::buy_tenant_domain, bajo confirmación manual de SuperAdmin.
"""
from __future__ import annotations

import secrets as _secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select

from core.config import settings as app_settings
from core.limiter import limiter
from database.models import Settings, Tenant, TenantDomain, User
from database.session import get_session
from web.compat_templates import CompatTemplates
from web.dependencies import get_settings, get_tenant, require_auth

router = APIRouter(tags=["Panel Dominios"])


def _templates():
    return CompatTemplates(directory="templates")


@router.get("/panel/dominios", response_class=HTMLResponse)
def panel_domains_page(
    request: Request,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    tenant = session.get(Tenant, tenant_id)
    if not tenant or not (tenant.has_ecommerce or tenant.has_landing):
        raise HTTPException(403, "Tu cuenta no tiene contratado Ecommerce ni Landing")

    domains = session.exec(select(TenantDomain).where(TenantDomain.tenant_id == tenant_id)).all()
    return _templates().TemplateResponse(
        "panel_dominios.html",
        {"request": request, "user": user, "settings": settings, "domains": domains},
    )


@router.get("/panel/dominios/disponibilidad")
@limiter.limit(app_settings.RATE_LIMIT_PUBLIC)
async def panel_domains_check(
    request: Request,
    dominio: str,
    user: User = Depends(require_auth),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    from services.domain_registrar_service import DomainRegistrarError, GoDaddyClient

    dominio_clean = dominio.strip().lower()
    if not dominio_clean or "." not in dominio_clean:
        return {"domain": dominio_clean, "available": False, "reason": "Dominio inválido"}

    existing = session.exec(select(TenantDomain).where(TenantDomain.domain == dominio_clean)).first()
    if existing:
        return {"domain": dominio_clean, "available": False, "reason": "Ese dominio ya está registrado en la plataforma"}

    try:
        client = GoDaddyClient()
        disponible = await client.check_availability(dominio_clean)
    except DomainRegistrarError as exc:
        return {"domain": dominio_clean, "available": False, "reason": str(exc)}

    return {"domain": dominio_clean, "available": disponible, "reason": None if disponible else "No disponible"}


@router.post("/panel/dominios/solicitar")
@limiter.limit(app_settings.RATE_LIMIT_LOGIN)
def panel_domains_request(
    request: Request,
    domain: str = Form(...),
    user: User = Depends(require_auth),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    tenant = session.get(Tenant, tenant_id)
    if not tenant or not (tenant.has_ecommerce or tenant.has_landing):
        raise HTTPException(403, "Tu cuenta no tiene contratado Ecommerce ni Landing")

    domain_clean = domain.strip().lower()
    if not domain_clean or "." not in domain_clean:
        raise HTTPException(400, "Dominio inválido")

    existing = session.exec(select(TenantDomain).where(TenantDomain.domain == domain_clean)).first()
    if existing:
        raise HTTPException(400, "Ese dominio ya está registrado en la plataforma")

    td = TenantDomain(
        tenant_id=tenant_id,
        domain=domain_clean,
        verification_token=_secrets.token_hex(16),
        status="purchase_requested",
    )
    session.add(td)
    session.commit()
    return {"status": "success", "domain": domain_clean}
