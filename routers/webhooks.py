"""routers/webhooks.py — Endpoints públicos de webhook para pasarelas de pago.

SIN JWT, SIN CSRF. Validación por firma HMAC.
Idempotencia sobre la TRANSICIÓN de estado (event_id + status_transition).
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from database.models import (
    PlatformPayment,
    ProcessedWebhook,
    Sale,
    Tenant,
)
from database.session import get_session
from services.payment_service import get_provider

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


def _already_processed(session: Session, event_id: str, source: str, transition: str) -> bool:
    existing = session.exec(
        select(ProcessedWebhook).where(
            ProcessedWebhook.event_id == event_id,
            ProcessedWebhook.source == source,
            ProcessedWebhook.status_transition == transition,
        )
    ).first()
    return existing is not None


def _record_processed(session: Session, event_id: str, source: str, transition: str) -> None:
    session.add(ProcessedWebhook(
        event_id=event_id,
        source=source,
        status_transition=transition,
        status="processed",
    ))


def _map_status(provider_status: str) -> str:
    mapping = {
        "COMPLETED": "paid",
        "PENDING": "pending",
        "FAILED": "failed",
        "CANCELLED": "cancelled",
        "REFUNDED": "refunded",
        "CHARGED_BACK": "charged_back",
    }
    return mapping.get(provider_status, "failed")


def _return_stock(session: Session, sale: Sale) -> None:
    """Devuelve stock al cancelar/reembolsar una venta."""
    from database.models import BinStock, StockMovement
    for item in sale.items:
        if not item.product_id:
            continue
        bin_stock = session.exec(
            select(BinStock).where(
                BinStock.product_id == item.product_id,
                BinStock.tenant_id == sale.tenant_id,
            )
        ).first()
        if bin_stock:
            bin_stock.quantity += item.quantity
            session.add(bin_stock)
            session.add(StockMovement(
                tenant_id=sale.tenant_id,
                product_id=item.product_id,
                to_bin_id=bin_stock.bin_id,
                quantity=item.quantity,
                reason="devolucion",
                notes=f"Reembolso/cancelación venta #{sale.id}",
            ))


def _process_payment_update(
    session: Session,
    payment: PlatformPayment,
    new_status: str,
    event_id: str,
    source: str,
    verified_amount: Decimal | None = None,
    verified_currency: str | None = None,
) -> bool:
    """Aplica la transición de estado. Retorna True si se procesó."""
    old_status = payment.status
    transition = f"{old_status}→{new_status}"

    if old_status == new_status:
        return False

    if _already_processed(session, event_id, source, transition):
        logger.info("Webhook already processed: %s %s", event_id, transition)
        return False

    if verified_amount is not None and verified_amount != payment.amount:
        logger.error(
            "Amount mismatch: expected %s, got %s (payment %s)",
            payment.amount, verified_amount, payment.id,
        )
        return False

    if verified_currency and verified_currency.upper() != payment.currency.upper():
        logger.error(
            "Currency mismatch: expected %s, got %s (payment %s)",
            payment.currency, verified_currency, payment.id,
        )
        return False

    payment.status = new_status

    if new_status == "paid":
        payment.completed_at = datetime.now(timezone.utc)
        _apply_paid_effects(session, payment)

    elif new_status in ("cancelled", "refunded", "charged_back"):
        if payment.sale_id:
            sale = session.get(Sale, payment.sale_id)
            if sale and sale.payment_status == "pagado":
                sale.payment_status = "reembolsado" if new_status == "refunded" else "cancelado"
                session.add(sale)
                _return_stock(session, sale)

    session.add(payment)
    _record_processed(session, event_id, source, transition)
    return True


def _apply_paid_effects(session: Session, payment: PlatformPayment) -> None:
    """Efectos de un pago completado según tipo."""
    meta = json.loads(payment.metadata_json or "{}")

    if payment.payment_type == "credits":
        credits = meta.get("credits", 0)
        tenant = session.get(Tenant, payment.tenant_id)
        if tenant and credits:
            tenant.ai_credits += credits
            session.add(tenant)

    elif payment.payment_type == "plan_upgrade":
        plan_name = meta.get("plan", "")
        credits = meta.get("credits", 0)
        tenant = session.get(Tenant, payment.tenant_id)
        if tenant:
            tenant.ai_tier = plan_name
            tenant.ai_credits += credits
            session.add(tenant)

    elif payment.payment_type == "storefront_checkout":
        if payment.sale_id:
            sale = session.get(Sale, payment.sale_id)
            if sale:
                sale.payment_status = "pagado"
                session.add(sale)

    elif payment.payment_type == "subscription":
        plan_name = meta.get("plan", "")
        credits = meta.get("credits", 0)
        tenant = session.get(Tenant, payment.tenant_id)
        if tenant:
            tenant.ai_tier = plan_name
            tenant.ai_credits += credits
            session.add(tenant)


# ── Mercado Pago ──────────────────────────────────────────────────────────

@router.post("/mercadopago")
async def webhook_mercadopago(request: Request, session: Session = Depends(get_session)):
    body = await request.body()
    headers = dict(request.headers)

    try:
        provider = get_provider("mercadopago")
    except ValueError:
        raise HTTPException(503, "MercadoPago not configured")

    payload = provider.verify_webhook(headers, body)
    if payload is None:
        raise HTTPException(400, "Invalid signature")

    action = payload.get("action", "")
    topic = payload.get("type", payload.get("topic", ""))

    if topic != "payment" and action not in ("payment.created", "payment.updated"):
        return Response(status_code=200)

    mp_payment_id = str(payload.get("data", {}).get("id", ""))
    if not mp_payment_id:
        return Response(status_code=200)

    info = await provider.get_payment_info(mp_payment_id)
    new_status = _map_status(info.status)
    ext_ref = info.raw.get("external_reference", "")

    payment = session.exec(
        select(PlatformPayment).where(
            PlatformPayment.external_ref == ext_ref,
            PlatformPayment.provider == "mercadopago",
        )
    ).first()

    if not payment:
        payment = session.exec(
            select(PlatformPayment).where(
                PlatformPayment.external_id == str(info.raw.get("preference_id", "")),
                PlatformPayment.provider == "mercadopago",
            )
        ).first()

    if not payment:
        logger.warning("MP webhook: no matching payment for ref=%s", ext_ref)
        return Response(status_code=200)

    if payment.external_id != mp_payment_id:
        payment.external_id = mp_payment_id
        session.add(payment)

    event_id = f"mp_{mp_payment_id}"
    _process_payment_update(
        session, payment, new_status, event_id, "mercadopago",
        verified_amount=info.amount, verified_currency=info.currency,
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        logger.info("MP webhook race: duplicate %s already committed", event_id)

    return Response(status_code=200)


# ── Stripe ────────────────────────────────────────────────────────────────

@router.post("/stripe")
async def webhook_stripe(request: Request, session: Session = Depends(get_session)):
    body = await request.body()
    headers = dict(request.headers)

    try:
        provider = get_provider("stripe")
    except ValueError:
        raise HTTPException(503, "Stripe not configured")

    payload = provider.verify_webhook(headers, body)
    if payload is None:
        raise HTTPException(400, "Invalid signature")

    event_type = payload.get("type", "")
    if event_type not in (
        "checkout.session.completed",
        "checkout.session.expired",
        "charge.refunded",
        "charge.dispute.created",
    ):
        return Response(status_code=200)

    event_id = payload.get("id", "")
    obj = payload.get("data", {}).get("object", {})
    session_id = obj.get("id", "")

    status_map = {
        "checkout.session.completed": "paid",
        "checkout.session.expired": "cancelled",
        "charge.refunded": "refunded",
        "charge.dispute.created": "charged_back",
    }
    new_status = status_map.get(event_type, "failed")

    payment = session.exec(
        select(PlatformPayment).where(
            PlatformPayment.external_id == session_id,
            PlatformPayment.provider == "stripe",
        )
    ).first()

    if not payment:
        client_ref = obj.get("client_reference_id", "")
        if client_ref:
            payment = session.exec(
                select(PlatformPayment).where(
                    PlatformPayment.external_ref == client_ref,
                    PlatformPayment.provider == "stripe",
                )
            ).first()

    if not payment:
        logger.warning("Stripe webhook: no matching payment for session=%s", session_id)
        return Response(status_code=200)

    amount = None
    if obj.get("amount_total"):
        amount = Decimal(str(obj["amount_total"])) / 100

    _process_payment_update(
        session, payment, new_status, event_id, "stripe",
        verified_amount=amount,
        verified_currency=obj.get("currency", "").upper() or None,
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        logger.info("Stripe webhook race: duplicate %s already committed", event_id)

    return Response(status_code=200)
