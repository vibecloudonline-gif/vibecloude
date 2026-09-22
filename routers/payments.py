"""routers/payments.py — Pasarelas de pago para la plataforma.

Tres flujos, un solo router:
1. Compra de créditos de IA (pago único)
2. Upgrade de plan (Free → Starter → Growth, pago único por ahora)
3. Checkout del storefront (el cliente final del tenant paga su pedido)

Cada flujo: crear orden → redirect a PayPal/Stripe → callback captura → efecto.
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from database.models import PlatformPayment, Sale, Settings, Tenant
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

PLANS = {
    "starter": {"price": Decimal("15.00"), "credits": 500, "label": "Starter"},
    "growth": {"price": Decimal("39.00"), "credits": 2000, "label": "Growth"},
}


def _templates():
    return CompatTemplates(directory="templates")


# ── 1. Créditos de IA ──────────────────────────────────────────────────────

class CreditPurchaseRequest(BaseModel):
    credits: int = 100
    provider: str = "paypal"


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

    base = str(request.base_url).rstrip("/")
    result = await provider.create_order(
        amount=amount,
        currency="USD",
        description=f"VibeCloud — {req.credits} créditos de IA",
        return_url=f"{base}/payments/credits/capture?provider={req.provider}",
        cancel_url=f"{base}/panel/creditos",
    )

    payment = PlatformPayment(
        tenant_id=tenant_id,
        provider=req.provider,
        external_id=result.external_id,
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
    provider: str = "paypal",
    db: Session = Depends(get_session),
):
    external_id = token or request.query_params.get("session_id", "")
    if not external_id:
        raise HTTPException(400, "Falta el ID de la transacción")

    payment = db.exec(
        select(PlatformPayment).where(
            PlatformPayment.external_id == external_id,
            PlatformPayment.payment_type == "credits",
        )
    ).first()
    if not payment:
        raise HTTPException(404, "Pago no encontrado")
    if payment.status == "completed":
        return RedirectResponse(url="/panel/creditos?status=already_completed", status_code=303)

    prov = get_provider(provider)
    capture = await prov.capture_order(external_id)

    if capture.status == "COMPLETED":
        meta = json.loads(payment.metadata_json)
        credits = meta.get("credits", 0)

        tenant = db.get(Tenant, payment.tenant_id)
        if tenant:
            tenant.ai_credits += credits
            db.add(tenant)

        payment.status = "completed"
        from datetime import datetime, timezone
        payment.completed_at = datetime.now(timezone.utc)
        db.add(payment)
        db.commit()

        return RedirectResponse(url=f"/panel/creditos?status=success&credits={credits}", status_code=303)

    payment.status = "failed"
    db.add(payment)
    db.commit()
    return RedirectResponse(url="/panel/creditos?status=failed", status_code=303)


# ── 2. Upgrade de plan ─────────────────────────────────────────────────────

class PlanUpgradeRequest(BaseModel):
    plan: str
    provider: str = "paypal"


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

    base = str(request.base_url).rstrip("/")
    result = await provider.create_order(
        amount=plan["price"],
        currency="USD",
        description=f"VibeCloud — Plan {plan['label']}",
        return_url=f"{base}/payments/plan/capture?provider={req.provider}",
        cancel_url=f"{base}/panel/planes",
    )

    payment = PlatformPayment(
        tenant_id=tenant_id,
        provider=req.provider,
        external_id=result.external_id,
        payment_type="plan_upgrade",
        amount=plan["price"],
        currency="USD",
        status="pending",
        description=f"Upgrade a {plan['label']}",
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
    provider: str = "paypal",
    db: Session = Depends(get_session),
):
    external_id = token or request.query_params.get("session_id", "")
    if not external_id:
        raise HTTPException(400, "Falta el ID de la transacción")

    payment = db.exec(
        select(PlatformPayment).where(
            PlatformPayment.external_id == external_id,
            PlatformPayment.payment_type == "plan_upgrade",
        )
    ).first()
    if not payment:
        raise HTTPException(404, "Pago no encontrado")
    if payment.status == "completed":
        return RedirectResponse(url="/panel/planes?status=already_completed", status_code=303)

    prov = get_provider(provider)
    capture = await prov.capture_order(external_id)

    if capture.status == "COMPLETED":
        meta = json.loads(payment.metadata_json)
        plan_name = meta.get("plan", "")
        credits = meta.get("credits", 0)

        tenant = db.get(Tenant, payment.tenant_id)
        if tenant:
            tenant.ai_tier = plan_name
            tenant.ai_credits += credits
            db.add(tenant)

        payment.status = "completed"
        from datetime import datetime, timezone
        payment.completed_at = datetime.now(timezone.utc)
        db.add(payment)
        db.commit()

        return RedirectResponse(url=f"/panel/planes?status=success&plan={plan_name}", status_code=303)

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
    provider_name = form.get("provider", "paypal")

    if not sale_id:
        raise HTTPException(400, "Falta sale_id")

    sale = db.exec(
        select(Sale).where(Sale.id == int(sale_id), Sale.tenant_id == tenant_id)
    ).first()
    if not sale:
        raise HTTPException(404, "Pedido no encontrado")
    if sale.payment_status == "pagado":
        return RedirectResponse(url=f"/tienda/pedido/{sale.id}?status=already_paid", status_code=303)

    provider = get_provider(provider_name)

    base = str(request.base_url).rstrip("/")
    result = await provider.create_order(
        amount=Decimal(str(sale.total_amount)),
        currency="USD",
        description=f"Pedido #{sale.id}",
        return_url=f"{base}/tienda/checkout/capturar?sale_id={sale.id}&provider={provider_name}",
        cancel_url=f"{base}/tienda/pedido/{sale.id}",
    )

    payment = PlatformPayment(
        tenant_id=tenant_id,
        provider=provider_name,
        external_id=result.external_id,
        payment_type="storefront_checkout",
        amount=Decimal(str(sale.total_amount)),
        currency="USD",
        status="pending",
        description=f"Pedido #{sale.id}",
        sale_id=sale.id,
    )
    db.add(payment)
    db.commit()

    return RedirectResponse(url=result.approve_url, status_code=303)


@router.get("/tienda/checkout/capturar")
async def storefront_capture_payment(
    request: Request,
    sale_id: int,
    token: Optional[str] = None,
    provider: str = "paypal",
    db: Session = Depends(get_session),
    tenant_id: int = Depends(get_public_tenant),
):
    external_id = token or request.query_params.get("session_id", "")
    if not external_id:
        raise HTTPException(400, "Falta el ID de la transacción")

    payment = db.exec(
        select(PlatformPayment).where(
            PlatformPayment.external_id == external_id,
            PlatformPayment.payment_type == "storefront_checkout",
            PlatformPayment.sale_id == sale_id,
        )
    ).first()
    if not payment:
        raise HTTPException(404, "Pago no encontrado")
    if payment.status == "completed":
        return RedirectResponse(url=f"/tienda/pedido/{sale_id}?status=paid", status_code=303)

    prov = get_provider(provider)
    capture = await prov.capture_order(external_id)

    if capture.status == "COMPLETED":
        sale = db.exec(
            select(Sale).where(Sale.id == sale_id, Sale.tenant_id == tenant_id)
        ).first()
        if sale:
            sale.payment_status = "pagado"
            db.add(sale)

        payment.status = "completed"
        from datetime import datetime, timezone
        payment.completed_at = datetime.now(timezone.utc)
        db.add(payment)
        db.commit()

        return RedirectResponse(url=f"/tienda/pedido/{sale_id}?status=paid", status_code=303)

    payment.status = "failed"
    db.add(payment)
    db.commit()
    return RedirectResponse(url=f"/tienda/pedido/{sale_id}?status=failed", status_code=303)


# ── Info ────────────────────────────────────────────────────────────────────

@router.get("/api/v1/payments/providers")
async def list_providers():
    return {"providers": get_available_providers()}


@router.get("/api/v1/payments/credits/packs")
async def list_credit_packs():
    return {"packs": {str(k): str(v) for k, v in CREDIT_PACKS.items()}}


@router.get("/api/v1/payments/plans")
async def list_plans():
    return {
        "plans": {
            name: {"price": str(p["price"]), "credits": p["credits"], "label": p["label"]}
            for name, p in PLANS.items()
        }
    }
