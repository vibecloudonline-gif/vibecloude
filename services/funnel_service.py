"""services/funnel_service.py — Tracking de eventos del embudo de conversión.

Cada evento es idempotente por (tenant_id, event_type): si ya existe, no se
duplica. Esto permite llamar track_event() sin miedo en cualquier punto del
flujo sin chequear primero si ya se registró.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from database.models import FUNNEL_EVENT_TYPES, FunnelEvent

logger = logging.getLogger("funnel_service")


def track_event(
    session: Session,
    tenant_id: int,
    event_type: str,
    user_id: Optional[int] = None,
    metadata: Optional[dict] = None,
) -> Optional[FunnelEvent]:
    if event_type not in FUNNEL_EVENT_TYPES:
        logger.warning("Tipo de evento de embudo desconocido: %s", event_type)
        return None

    existing = session.exec(
        select(FunnelEvent).where(
            FunnelEvent.tenant_id == tenant_id,
            FunnelEvent.event_type == event_type,
        )
    ).first()
    if existing:
        return existing

    event = FunnelEvent(
        tenant_id=tenant_id,
        user_id=user_id,
        event_type=event_type,
        metadata_json=json.dumps(metadata) if metadata else None,
    )
    session.add(event)
    try:
        session.commit()
        session.refresh(event)
        logger.info("Evento de embudo registrado: tenant=%d type=%s", tenant_id, event_type)
        return event
    except IntegrityError:
        session.rollback()
        return session.exec(
            select(FunnelEvent).where(
                FunnelEvent.tenant_id == tenant_id,
                FunnelEvent.event_type == event_type,
            )
        ).first()


def get_funnel_status(session: Session, tenant_id: int) -> dict:
    events = session.exec(
        select(FunnelEvent).where(FunnelEvent.tenant_id == tenant_id)
    ).all()

    event_map = {e.event_type: e for e in events}
    status = {}
    for evt_type in FUNNEL_EVENT_TYPES:
        evt = event_map.get(evt_type)
        status[evt_type] = {
            "completed": evt is not None,
            "date": evt.created_at.isoformat() if evt else None,
        }
    return status
