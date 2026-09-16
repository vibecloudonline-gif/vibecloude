from __future__ import annotations

import json
import logging
from typing import Optional

from sqlmodel import Session, select

from database.models import Offer, ResearchProject

logger = logging.getLogger("offer_service")


async def generate_offer(session: Session, project: ResearchProject, tenant_id: int) -> Offer:
    from services.ai.contracts import AIMessage, AIRequest
    from services.ai.gateway import ai_gateway

    listings_desc = "\n".join(
        f"- {l.title}: ${l.price} ({l.source}, rating {l.rating}, {l.review_count} reviews)"
        for l in project.listings if l.price
    )
    demand_desc = ""
    if project.demand:
        demand_desc = (
            f"\nDemanda: confianza={project.demand.confidence_level}, "
            f"volumen={project.demand.estimated_monthly_volume}/mes"
        )
    competitors_desc = ""
    if project.competitors:
        competitors_desc = "\nCompetidores:\n" + "\n".join(
            f"- {c.url}: {c.value_proposition or 'sin datos'}"
            for c in project.competitors
        )
    factory_info = ""
    if project.factory_price:
        factory_info = f"\nPrecio de fabrica/costo: ${project.factory_price}"

    system_prompt = (
        "Sos un estratega de negocios. Dada la investigacion de mercado de un producto/servicio, "
        "genera una oferta comercial optimizada. Responde SOLO con un objeto JSON con estas claves exactas:\n"
        '{"title": "nombre de la oferta", "value_proposition": "propuesta de valor en 2-3 oraciones", '
        '"price_structure": "estructura de precio sugerida", "cta_text": "texto del boton de compra", '
        '"differentiators": ["diferenciador 1", "diferenciador 2", ...]}\n'
        "No agregues texto fuera del JSON."
    )
    user_prompt = (
        f"Producto/servicio: {project.query_description}\n"
        f"Tipo: {project.project_type}\n"
        f"Listados comparables:\n{listings_desc}"
        f"{demand_desc}{factory_info}{competitors_desc}"
    )

    request = AIRequest(
        task="offer_generation",
        messages=[AIMessage(role="user", content=user_prompt)],
        system_prompt=system_prompt,
        provider="claude",
        max_tokens=1024,
        timeout=30.0,
    )

    errors: list[str] = []
    for provider in ("claude", "gemini", "qwen"):
        try:
            request.provider = provider
            if provider == "qwen":
                request.model = "qwen-plus"
            response = await ai_gateway.generate(request)
            raw = response.content.strip()
            if raw.startswith("```"):
                raw = raw.strip("`")
                if raw.lower().startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            parsed = json.loads(raw)
            break
        except Exception as exc:
            errors.append(f"{provider}: {exc}")
            parsed = None

    if parsed is None:
        raise RuntimeError("Ningun proveedor de IA pudo generar la oferta. " + " | ".join(errors))

    existing_count = session.exec(
        select(Offer).where(Offer.project_id == project.id, Offer.tenant_id == tenant_id)
    ).all()
    version = len(existing_count) + 1

    offer = Offer(
        tenant_id=tenant_id,
        project_id=project.id,
        title=str(parsed.get("title", project.query_description[:80])),
        value_proposition=str(parsed.get("value_proposition", "")),
        price_structure=str(parsed.get("price_structure", "")),
        cta_text=str(parsed.get("cta_text", "Comprar ahora")),
        differentiators_json=json.dumps(parsed.get("differentiators", []), ensure_ascii=False),
        status="draft",
        version=version,
    )
    session.add(offer)
    session.commit()
    session.refresh(offer)
    return offer


def get_offer(session: Session, offer_id: int, tenant_id: int) -> Optional[Offer]:
    offer = session.exec(
        select(Offer).where(Offer.id == offer_id, Offer.tenant_id == tenant_id)
    ).first()
    if offer:
        _ = offer.debate
    return offer


def get_latest_offer_for_project(session: Session, project_id: int, tenant_id: int) -> Optional[Offer]:
    return session.exec(
        select(Offer)
        .where(Offer.project_id == project_id, Offer.tenant_id == tenant_id)
        .order_by(Offer.version.desc())
    ).first()
