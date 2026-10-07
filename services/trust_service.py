"""services/trust_service.py — Anti-fraude, comisiones y métricas de confianza"""
import hashlib
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import Session, select, func, or_
from database.models import (
    Sale, Tenant, Client, OrderFingerprint, ReturnRequest,
    TrustMetrics, BusinessProfile,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def calculate_commission(sale_total: Decimal, commission_pct: Decimal) -> Decimal:
    return (sale_total * commission_pct / Decimal("100")).quantize(Decimal("0.01"))


def record_sale_commission(session: Session, sale: Sale) -> None:
    tenant = session.get(Tenant, sale.tenant_id)
    if not tenant:
        return
    sale.platform_commission = calculate_commission(
        sale.total_amount, tenant.platform_commission_pct
    )


def create_fingerprint(
    session: Session,
    sale: Sale,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    session_id: Optional[str] = None,
    buyer_email: Optional[str] = None,
    buyer_cuit: Optional[str] = None,
) -> OrderFingerprint:
    device_hash = None
    if ip and user_agent:
        raw = f"{ip}:{user_agent}"
        device_hash = hashlib.sha256(raw.encode()).hexdigest()[:16]

    fp = OrderFingerprint(
        sale_id=sale.id,
        tenant_id=sale.tenant_id,
        buyer_ip=ip,
        buyer_user_agent=user_agent,
        buyer_session_id=session_id,
        buyer_device_hash=device_hash,
        buyer_email=buyer_email,
        buyer_cuit=buyer_cuit,
    )

    fraud_reasons = []
    fraud_score = 0

    tenant = session.get(Tenant, sale.tenant_id)
    if tenant:
        settings_user = None
        if sale.user_id:
            from database.models import User
            settings_user = session.get(User, sale.user_id)
        if settings_user and settings_user.tenant_id == sale.tenant_id:
            if sale.client_id:
                client = session.get(Client, sale.client_id)
                if client:
                    if buyer_email and client.email and buyer_email.lower() == client.email.lower():
                        pass
                    owner_profile = session.exec(
                        select(BusinessProfile).where(BusinessProfile.tenant_id == sale.tenant_id)
                    ).first()
                    if owner_profile:
                        if buyer_cuit and client.cuit and buyer_cuit == client.cuit:
                            fraud_reasons.append("cuit_match_owner")
                            fraud_score += 40

        if device_hash:
            prev = session.exec(
                select(OrderFingerprint).where(
                    OrderFingerprint.tenant_id == sale.tenant_id,
                    OrderFingerprint.buyer_device_hash == device_hash,
                    OrderFingerprint.sale_id != sale.id,
                ).limit(1)
            ).first()
            if prev:
                fraud_reasons.append("repeated_device")
                fraud_score += 20

        if buyer_ip:
            seller_fps = session.exec(
                select(OrderFingerprint).where(
                    OrderFingerprint.tenant_id == sale.tenant_id,
                    OrderFingerprint.buyer_ip == buyer_ip,
                ).limit(5)
            ).all()
            if len(seller_fps) >= 3:
                fraud_reasons.append("ip_cluster")
                fraud_score += 30

    fp.fraud_score = fraud_score
    fp.fraud_reasons = ",".join(fraud_reasons) if fraud_reasons else None
    fp.is_self_purchase = fraud_score >= 40

    if fraud_score >= 40:
        sale.fraud_flag = "suspicious"

    session.add(fp)
    return fp


def refresh_trust_metrics(session: Session, tenant_id: int) -> TrustMetrics:
    metrics = session.exec(
        select(TrustMetrics).where(TrustMetrics.tenant_id == tenant_id)
    ).first()
    if not metrics:
        metrics = TrustMetrics(tenant_id=tenant_id)
        session.add(metrics)

    total_sales = session.exec(
        select(func.count(Sale.id)).where(Sale.tenant_id == tenant_id)
    ).one()

    unique_buyers = session.exec(
        select(func.count(func.distinct(Sale.client_id))).where(
            Sale.tenant_id == tenant_id, Sale.client_id != None
        )
    ).one()

    total_revenue = session.exec(
        select(func.coalesce(func.sum(Sale.total_amount), 0)).where(
            Sale.tenant_id == tenant_id
        )
    ).one()

    total_commission = session.exec(
        select(func.coalesce(func.sum(Sale.platform_commission), 0)).where(
            Sale.tenant_id == tenant_id
        )
    ).one()

    return_count = session.exec(
        select(func.count(ReturnRequest.id)).where(
            ReturnRequest.tenant_id == tenant_id
        )
    ).one()

    complaint_count = session.exec(
        select(func.count(ReturnRequest.id)).where(
            ReturnRequest.tenant_id == tenant_id,
            ReturnRequest.reason == "complaint",
        )
    ).one()

    self_purchase_count = session.exec(
        select(func.count(OrderFingerprint.id)).where(
            OrderFingerprint.tenant_id == tenant_id,
            OrderFingerprint.is_self_purchase == True,
        )
    ).one()

    fraud_flags = session.exec(
        select(func.count(Sale.id)).where(
            Sale.tenant_id == tenant_id,
            Sale.fraud_flag != None,
        )
    ).one()

    metrics.total_sales = total_sales
    metrics.unique_buyers = unique_buyers
    metrics.total_revenue = Decimal(str(total_revenue))
    metrics.total_commission = Decimal(str(total_commission))
    metrics.return_count = return_count
    metrics.complaint_count = complaint_count
    metrics.self_purchase_count = self_purchase_count
    metrics.fraud_flags_count = fraud_flags

    if total_sales > 0:
        metrics.return_rate_pct = Decimal(
            str(round(return_count / total_sales * 100, 2))
        )
    else:
        metrics.return_rate_pct = Decimal("0.00")

    metrics.updated_at = _utcnow()
    return metrics


def check_verified_purchase(session: Session, reviewer_tenant_id: int, seller_tenant_id: int) -> bool:
    from database.models import User
    reviewer_users = session.exec(
        select(User.id).where(User.tenant_id == reviewer_tenant_id)
    ).all()
    if not reviewer_users:
        return False
    sale = session.exec(
        select(Sale).where(
            Sale.tenant_id == seller_tenant_id,
            Sale.user_id.in_(reviewer_users),
        ).limit(1)
    ).first()
    return sale is not None
