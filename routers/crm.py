"""routers/crm.py — Panel de integracion CRM"""
import json
from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select
from database.session import get_session
from database.models import (
    AICredential, CRMSyncLog, Settings, User,
    encrypt_api_key,
)
from services.entitlements import can_use_module, get_blocked_message
from web.dependencies import require_auth, get_tenant, get_settings
from web.compat_templates import CompatTemplates
from services.crm_service import CRMSyncService

router = APIRouter(tags=["CRM"])

def _templates():
    return CompatTemplates(directory="templates")


def _get_crm_config(session: Session, tenant_id: int) -> dict:
    settings = session.exec(
        select(Settings).where(Settings.tenant_id == tenant_id)
    ).first()
    if settings and settings.site_config_json:
        try:
            cfg = json.loads(settings.site_config_json) if isinstance(settings.site_config_json, str) else settings.site_config_json
            return cfg
        except Exception:
            pass
    return {}


@router.get("/panel/crm", response_class=HTMLResponse)
def panel_crm_dashboard(
    request: Request,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    from database.models import Tenant
    tenant = session.get(Tenant, tenant_id)
    if not tenant or not can_use_module(tenant, "crm"):
        raise HTTPException(403, get_blocked_message("crm"))
    cred = session.exec(
        select(AICredential).where(
            AICredential.tenant_id == tenant_id,
            AICredential.provider == "crm",
        )
    ).first()
    cfg = _get_crm_config(session, tenant_id)
    crm_url = cfg.get("crm_base_url", "")
    is_configured = bool(cred and crm_url)
    logs = session.exec(
        select(CRMSyncLog).where(CRMSyncLog.tenant_id == tenant_id)
        .order_by(CRMSyncLog.created_at.desc()).limit(20)
    ).all()
    return _templates().TemplateResponse("panel_crm.html", {
        "request": request, "user": user, "settings": settings,
        "active_page": "crm", "is_configured": is_configured,
        "crm_url": crm_url, "has_key": bool(cred), "logs": logs,
    })


@router.post("/panel/crm/config")
def panel_crm_save_config(
    request: Request,
    crm_base_url: str = Form(...),
    crm_api_key: str = Form(""),
    user: User = Depends(require_auth),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    settings = session.exec(
        select(Settings).where(Settings.tenant_id == tenant_id)
    ).first()
    if settings:
        try:
            cfg = json.loads(settings.site_config_json) if settings.site_config_json else {}
        except Exception:
            cfg = {}
        cfg["crm_base_url"] = crm_base_url.rstrip("/")
        settings.site_config_json = json.dumps(cfg)
        session.add(settings)

    if crm_api_key.strip():
        cred = session.exec(
            select(AICredential).where(
                AICredential.tenant_id == tenant_id,
                AICredential.provider == "crm",
            )
        ).first()
        if cred:
            cred.api_key_enc = encrypt_api_key(crm_api_key.strip())
            session.add(cred)
        else:
            cred = AICredential(
                tenant_id=tenant_id,
                provider="crm",
                api_key_enc=encrypt_api_key(crm_api_key.strip()),
            )
            session.add(cred)
    session.commit()
    return RedirectResponse("/panel/crm", status_code=302)


@router.post("/panel/crm/sync")
def panel_crm_trigger_sync(
    request: Request,
    sync_type: str = Form("full"),
    user: User = Depends(require_auth),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    svc = CRMSyncService.from_tenant(session, tenant_id)
    if not svc:
        raise HTTPException(400, "CRM no configurado. Configurá la URL y API key primero.")
    if sync_type == "pull_contacts":
        svc.pull_contacts()
    elif sync_type == "push_contacts":
        svc.push_contacts()
    elif sync_type == "push_sales":
        svc.push_sales()
    else:
        svc.full_sync()
    return RedirectResponse("/panel/crm", status_code=302)


@router.get("/panel/crm/log", response_class=HTMLResponse)
def panel_crm_log(
    request: Request,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    tenant_id: int = Depends(get_tenant),
    session: Session = Depends(get_session),
):
    logs = session.exec(
        select(CRMSyncLog).where(CRMSyncLog.tenant_id == tenant_id)
        .order_by(CRMSyncLog.created_at.desc()).limit(50)
    ).all()
    return _templates().TemplateResponse("panel_crm.html", {
        "request": request, "user": user, "settings": settings,
        "active_page": "crm", "is_configured": True,
        "crm_url": "", "has_key": True, "logs": logs, "show_log": True,
    })
