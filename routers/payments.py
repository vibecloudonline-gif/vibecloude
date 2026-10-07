"""routers/payments.py — Pasarelas de pago para la plataforma.

Tres flujos:
1. Compra de créditos de IA (pago único, cuenta de la plataforma)
2. Suscripción de plan (Inicial/Tienda/Comercio, cuenta de la plataforma)
3. Checkout del storefront (pago a la cuenta DEL COMERCIO con comisión)
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from database.models import (
    PlatformPayment,
    Sale,
    Settings,
    Tenant,
    TenantPaymentConfig,
    decrypt_api_key,
)
from database.session import get_session
from services.payment_service import get_available_providers, get_provider
from web.compat_templates import CompatTemplates
from web.dependencies import get_current_tenant, get_public_tenant, require_auth

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Payments"])

CREDIT_PACKS = {
    100: Decimal("2.99"),
    500: Decimal("9.99"),
    1000: Decimal("17.99"),
    2500: Decimal("39.99"),
}

from services.plan_service import PLAN_DEFINITIONS

PLANS = {
    slug: {"price": p["price"], "credits": p["credits_per_month"], "label": p["label"]}
    for slug, p in PLAN_DEFINITIONS.items()
}


def _templates():
    return CompatTemplates(directory="templates")


def _make_ref() -> str:
    return uuid.uuid4().hex


def _get_merchant_token(session: Session, tenant_id: int, provider: str) -> str | None:
    config = session.exec(
        select(TenantPaymentConfig).where(
            TenantPaymentConfig.tenant_id == tenant_id,
            TenantPaymentConfig.provider == provider,
            TenantPaymentConfig.is_active == True,
        )
    ).first()
    if not config:
        return None
    return decrypt_api_key(config.access_token_enc)


def _calc_commission(tenant: Tenant, amount: Decimal) -> Decimal:
    pct = tenant.platform_commission_pct or Decimal("5.00")
    return (amount * pct / Decimal("100")).quantize(Decimal("0.01"))


# ── 1. Créditos de IA ──────────────────────────────────────────────────────

class CreditPurchaseRequest(BaseModel):
    credits: int = 100
    provider: str = "mercadopago"


@router.post("/api/v1/payments/credits/create")
async def create_credits_order(
    req: CreditPurchaseRequest,
    request: Request,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_current_tenant),
):
    if req.credits not in CREDIT_PACKS:
        raise HTTPException(400, f"Pack inválido. Opciones: {list(CREDIT_PACKS.keys())}")

    amount = CREDIT_PACKS[req.credits]
    provider = get_provider(req.provider)
    ext_ref = _make_ref()

    base = str(request.base_url).rstrip("/")
    result = await provider.create_order(
        amount=amount,
        currency="USD",
        description=f"VibeCloud — {req.credits} créditos de IA",
        return_url=f"{base}/payments/credits/capture?provider={req.provider}&ref={ext_ref}",
        cancel_url=f"{base}/panel/creditos",
        external_ref=ext_ref,
    )

    payment = PlatformPayment(
        tenant_id=tenant_id,
        provider=req.provider,
        external_id=result.external_id,
        external_ref=ext_ref,
        payment_type="credits",
        amount=amount,
        currency="USD",
        status="pending",
        description=f"{req.credits} créditos de IA",
        metadata_json=json.dumps({"credits": req.credits}),
    )
    db.add(payment)
    db.commit()

    return {
        "success": True,
        "approve_url": result.approve_url,
        "external_id": result.external_id,
    }


@router.get("/payments/credits/capture")
async def capture_credits_order(
    request: Request,
    token: Optional[str] = None,
    ref: Optional[str] = None,
    provider: str = "mercadopago",
    db: Session = Depends(get_session),
):
    external_id = token or request.query_params.get("session_id", "")

    payment = None
    if ref:
        payment = db.exec(
            select(PlatformPayment).where(
                PlatformPayment.external_ref == ref,
                PlatformPayment.payment_type == "credits",
            )
        ).first()
    if not payment and external_id:
        payment = db.exec(
            select(PlatformPayment).where(
                PlatformPayment.external_id == external_id,
                PlatformPayment.payment_type == "credits",
            )
        ).first()

    if not payment:
        raise HTTPException(404, "Pago no encontrado")
    if payment.status == "paid":
        return RedirectResponse(url="/panel/creditos?status=already_completed", status_code=303)

    prov = get_provider(provider)
    capture = await prov.capture_order(external_id or payment.external_id)

    if capture.status == "COMPLETED":
        payment.status = "captured"
        payment.completed_at = datetime.now(timezone.utc)
        db.add(payment)
        db.commit()

        return RedirectResponse(url="/panel/creditos?status=processing", status_code=303)

    payment.status = "failed"
    db.add(payment)
    db.commit()
    return RedirectResponse(url="/panel/creditos?status=failed", status_code=303)


# ── 2. Suscripción de plan ────────────────────────────────────────────────

class PlanUpgradeRequest(BaseModel):
    plan: str
    provider: str = "mercadopago"


@router.post("/api/v1/payments/plan/create")
async def create_plan_order(
    req: PlanUpgradeRequest,
    request: Request,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_current_tenant),
):
    if req.plan not in PLANS:
        raise HTTPException(400, f"Plan inválido. Opciones: {list(PLANS.keys())}")

    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant no encontrado")
    if tenant.ai_tier == req.plan:
        raise HTTPException(400, f"Ya estás en el plan {req.plan}")

    plan = PLANS[req.plan]
    provider = get_provider(req.provider)
    ext_ref = _make_ref()

    base = str(request.base_url).rstrip("/")
    result = await provider.create_order(
        amount=plan["price"],
        currency="USD",
        description=f"VibeCloud — Plan {plan['label']}",
        return_url=f"{base}/payments/plan/capture?provider={req.provider}&ref={ext_ref}",
        cancel_url=f"{base}/panel/planes",
        external_ref=ext_ref,
    )

    payment = PlatformPayment(
        tenant_id=tenant_id,
        provider=req.provider,
        external_id=result.external_id,
        external_ref=ext_ref,
        payment_type="subscription",
        amount=plan["price"],
        currency="USD",
        status="pending",
        description=f"Plan {plan['label']}",
        metadata_json=json.dumps({"plan": req.plan, "credits": plan["credits"]}),
    )
    db.add(payment)
    db.commit()

    return {
        "success": True,
        "approve_url": result.approve_url,
        "external_id": result.external_id,
    }


@router.get("/payments/plan/capture")
async def capture_plan_order(
    request: Request,
    token: Optional[str] = None,
    ref: Optional[str] = None,
    provider: str = "mercadopago",
    db: Session = Depends(get_session),
):
    external_id = token or request.query_params.get("session_id", "")

    payment = None
    if ref:
        payment = db.exec(
            select(PlatformPayment).where(
                PlatformPayment.external_ref == ref,
                PlatformPayment.payment_type == "subscription",
            )
        ).first()
    if not payment and external_id:
        payment = db.exec(
            select(PlatformPayment).where(
                PlatformPayment.external_id == external_id,
                PlatformPayment.payment_type == "subscription",
            )
        ).first()

    if not payment:
        raise HTTPException(404, "Pago no encontrado")
    if payment.status == "paid":
        return RedirectResponse(url="/panel/planes?status=already_completed", status_code=303)

    prov = get_provider(provider)
    capture = await prov.capture_order(external_id or payment.external_id)

    if capture.status == "COMPLETED":
        payment.status = "captured"
        payment.completed_at = datetime.now(timezone.utc)
        db.add(payment)
        db.commit()

        return RedirectResponse(url="/panel/planes?status=processing", status_code=303)

    payment.status = "failed"
    db.add(payment)
    db.commit()
    return RedirectResponse(url="/panel/planes?status=failed", status_code=303)


# ── 3. Checkout storefront ─────────────────────────────────────────────────

@router.post("/tienda/checkout/pagar")
async def storefront_create_payment(
    request: Request,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_public_tenant),
):
    form = await request.form()
    sale_id = form.get("sale_id")
    provider_name = form.get("provider", "mercadopago")

    if not sale_id:
        raise HTTPException(400, "Falta sale_id")

    sale = db.exec(
        select(Sale).where(Sale.id == int(sale_id), Sale.tenant_id == tenant_id)
    ).first()
    if not sale:
        raise HTTPException(404, "Pedido no encontrado")
    if sale.payment_status == "pagado":
        return RedirectResponse(url=f"/tienda/pedido/{sale.id}?status=already_paid", status_code=303)

    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant no encontrado")

    merchant_token = _get_merchant_token(db, tenant_id, provider_name)
    if not merchant_token:
        raise HTTPException(400, "El comercio no tiene pasarela de pago configurada.")

    provider = get_provider(provider_name)
    ext_ref = _make_ref()
    sale_amount = Decimal(str(sale.total_amount))
    commission = _calc_commission(tenant, sale_amount)

    base = str(request.base_url).rstrip("/")
    result = await provider.create_order(
        amount=sale_amount,
        currency="USD",
        description=f"Pedido #{sale.id}",
        return_url=f"{base}/tienda/checkout/capturar?ref={ext_ref}&provider={provider_name}",
        cancel_url=f"{base}/tienda/pedido/{sale.id}",
        external_ref=ext_ref,
        merchant_token=merchant_token,
        commission_amount=commission,
    )

    payment = PlatformPayment(
        tenant_id=tenant_id,
        provider=provider_name,
        external_id=result.external_id,
        external_ref=ext_ref,
        payment_type="storefront_checkout",
        amount=sale_amount,
        currency="USD",
        status="pending",
        description=f"Pedido #{sale.id}",
        sale_id=sale.id,
        commission_amount=commission,
    )
    db.add(payment)
    db.commit()

    return RedirectResponse(url=result.approve_url, status_code=303)


@router.get("/tienda/checkout/capturar")
async def storefront_capture_payment(
    request: Request,
    ref: Optional[str] = None,
    sale_id: Optional[int] = None,
    token: Optional[str] = None,
    provider: str = "mercadopago",
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_public_tenant),
):
    external_id = token or request.query_params.get("session_id", "")

    payment = None
    if ref:
        payment = db.exec(
            select(PlatformPayment).where(
                PlatformPayment.external_ref == ref,
                PlatformPayment.payment_type == "storefront_checkout",
            )
        ).first()
    if not payment and external_id:
        payment = db.exec(
            select(PlatformPayment).where(
                PlatformPayment.external_id == external_id,
                PlatformPayment.payment_type == "storefront_checkout",
            )
        ).first()

    if not payment:
        raise HTTPException(404, "Pago no encontrado")
    if payment.status == "paid":
        sid = payment.sale_id or sale_id or 0
        return RedirectResponse(url=f"/tienda/pedido/{sid}?status=paid", status_code=303)

    prov = get_provider(provider)
    capture = await prov.capture_order(external_id or payment.external_id)

    sid = payment.sale_id or sale_id or 0

    if capture.status == "COMPLETED":
        payment.status = "captured"
        payment.completed_at = datetime.now(timezone.utc)
        db.add(payment)
        db.commit()

        return RedirectResponse(url=f"/tienda/pedido/{sid}?status=processing", status_code=303)

    payment.status = "failed"
    db.add(payment)
    db.commit()
    return RedirectResponse(url=f"/tienda/pedido/{sid}?status=failed", status_code=303)


# ── Info ────────────────────────────────────────────────────────────────────

@router.get("/api/v1/payments/providers")
def list_providers():
    return {"providers": get_available_providers()}


@router.get("/api/v1/payments/credits/packs")
def list_credit_packs():
    return {"packs": {str(k): str(v) for k, v in CREDIT_PACKS.items()}}


@router.get("/api/v1/payments/plans")
def list_plans():
    return {
        "plans": {
            name: {"price": str(p["price"]), "credits": p["credits"], "label": p["label"]}
            for name, p in PLANS.items()
        }
    }


@router.get("/api/v1/payments/status/{ref}")
def get_payment_status(
    ref: str,
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_current_tenant),
):
    """Poll payment status by external_ref. Frontend uses this to detect webhook confirmation."""
    payment = db.exec(
        select(PlatformPayment).where(
            PlatformPayment.external_ref == ref,
            PlatformPayment.tenant_id == tenant_id,
        )
    ).first()
    if not payment:
        raise HTTPException(404, "Pago no encontrado")
    return {
        "status": payment.status,
        "payment_type": payment.payment_type,
        "completed_at": payment.completed_at.isoformat() if payment.completed_at else None,
    }
