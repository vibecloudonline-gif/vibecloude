from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, select

from database.models import DebateObjection, Offer, TenantProfile, ValidationDebate

logger = logging.getLogger("debate_service")

_DEBATE_PERSONAS = [
    {
        "id": "devil_advocate",
        "label": "Abogado del diablo",
        "role": (
            "Tu trabajo es encontrar la debilidad fatal de esta oferta. "
            "Busca el punto mas fragil: modelo de negocio insostenible, "
            "dependencia de un solo canal, barrera de entrada inexistente. "
            "Ademas de la objecion, propone una solucion practica para resolverla."
        ),
    },
    {
        "id": "price_skeptic",
        "label": "Esceptico de precio",
        "role": (
            "Evaluas si el precio propuesto tiene sentido frente a la "
            "competencia. Si esta caro, explica por que. Si esta barato, "
            "cuestiona si los margenes son viables. "
            "Ademas de la objecion, propone como ajustar el precio o la estructura de costos."
        ),
    },
    {
        "id": "market_analyst",
        "label": "Analista de mercado",
        "role": (
            "Miras el tamanio del mercado, la tendencia y la saturacion. "
            "Cuestiona si hay suficiente demanda o si el mercado ya esta "
            "copado por jugadores establecidos. "
            "Ademas de la objecion, propone una estrategia para diferenciarse o encontrar un nicho."
        ),
    },
    {
        "id": "customer_sim",
        "label": "Cliente simulado",
        "role": (
            "Sos un comprador potencial. Pensas en voz alta sobre por que "
            "comprarias o NO comprarias este producto/servicio. Se honesto "
            "sobre tus dudas. "
            "Ademas de la objecion, propone que cambiaria tu decision de compra."
        ),
    },
]


async def _run_persona_agent(
    persona: dict,
    offer_summary: str,
) -> Optional[dict]:
    from services.ai.contracts import AIError, AIMessage, AIRequest
    from services.ai.gateway import ai_gateway

    system_prompt = (
        f"Sos un evaluador de ofertas comerciales con este perfil: {persona['role']} "
        "Te presentan una oferta y debes formular UNA objecion concreta Y una solucion practica. "
        'Responde SOLO un objeto JSON: {"objection": "tu objecion en 1-2 oraciones", '
        '"severity": "high|medium|low", "proposed_solution": "solucion concreta en 1-2 oraciones"}. '
        "No agregues texto fuera del JSON."
    )

    request = AIRequest(
        task="debate_persona",
        messages=[AIMessage(role="user", content=offer_summary)],
        system_prompt=system_prompt,
        provider="gemini",
        timeout=20.0,
    )

    try:
        response = await ai_gateway.generate(request)
        raw = response.content.strip()
    except AIError:
        return None

    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
        return {
            "source": persona["id"],
            "label": persona["label"],
            "objection": str(parsed.get("objection", "")),
            "severity": str(parsed.get("severity", "medium")),
            "proposed_solution": str(parsed.get("proposed_solution", "")),
        }
    except (json.JSONDecodeError, KeyError):
        logger.warning("Persona %s devolvio respuesta no parseable: %s", persona["id"], raw[:200])
        return None


async def _run_arbiter(
    offer_summary: str,
    objections: list[dict],
) -> Optional[dict]:
    from services.ai.contracts import AIError, AIMessage, AIRequest
    from services.ai.gateway import ai_gateway

    objections_text = "\n".join(
        f"{i+1}. [{o['source']}] (severity: {o['severity']}): {o['objection']}"
        + (f" | Solucion propuesta: {o.get('proposed_solution', '')}" if o.get('proposed_solution') else "")
        for i, o in enumerate(objections)
    )

    system_prompt = (
        "Sos un arbitro de negocios senior. Recibes una oferta comercial, objeciones "
        "de distintos evaluadores y sus soluciones propuestas. Tu trabajo es:\n"
        "1. Para cada objecion, resolver si se acepta o se descarta, con una solucion concreta.\n"
        "2. Sintetizar un plan de accion con los 3 pasos mas importantes que el negocio debe tomar.\n"
        "Responde SOLO con un objeto JSON:\n"
        '{"resolutions": [{"index": 1, "status": "resolved|dismissed", "text": "solucion o razon"}], '
        '"action_plan": ["paso 1 concreto", "paso 2 concreto", "paso 3 concreto"], '
        '"verdict": "approved|needs_revision", "summary": "resumen de 2-3 oraciones"}\n'
        "No agregues texto fuera del JSON."
    )
    user_prompt = f"OFERTA:\n{offer_summary}\n\nOBJECIONES Y SOLUCIONES PROPUESTAS:\n{objections_text}"

    request = AIRequest(
        task="debate_arbiter",
        messages=[AIMessage(role="user", content=user_prompt)],
        system_prompt=system_prompt,
        provider="claude",
        max_tokens=1500,
        timeout=30.0,
    )

    errors: list[str] = []
    for provider in ("claude", "gemini"):
        try:
            request.provider = provider
            response = await ai_gateway.generate(request)
            raw = response.content.strip()
            if raw.startswith("```"):
                raw = raw.strip("`")
                if raw.lower().startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            return json.loads(raw)
        except Exception as exc:
            errors.append(f"{provider}: {exc}")

    logger.error("Arbiter failed on all providers: %s", " | ".join(errors))
    return None


async def run_debate(session: Session, offer: Offer) -> ValidationDebate:
    debate = ValidationDebate(
        offer_id=offer.id,
        status="in_progress",
    )
    session.add(debate)
    session.commit()
    session.refresh(debate)

    offer_summary = (
        f"Titulo: {offer.title}\n"
        f"Propuesta de valor: {offer.value_proposition}\n"
        f"Estructura de precio: {offer.price_structure}\n"
        f"CTA: {offer.cta_text}"
    )
    if offer.differentiators_json:
        try:
            diffs = json.loads(offer.differentiators_json)
            if diffs:
                offer_summary += "\nDiferenciadores: " + ", ".join(str(d) for d in diffs)
        except json.JSONDecodeError:
            pass

    profile = session.exec(
        select(TenantProfile).where(TenantProfile.tenant_id == offer.tenant_id)
    ).first()
    if profile and profile.elevator_pitch:
        offer_summary += (
            f"\n\nCONTEXTO DEL NEGOCIO:"
            f"\nPitch: {profile.elevator_pitch}"
            f"\nTipo: {profile.business_type}, Etapa: {profile.business_stage}"
        )
        if profile.target_audience:
            offer_summary += f"\nAudiencia: {profile.target_audience}"
        if profile.target_market:
            offer_summary += f"\nMercado: {profile.target_market}"
        if profile.main_challenge:
            offer_summary += f"\nDesafio: {profile.main_challenge}"
        if profile.competitors:
            offer_summary += f"\nCompetidores: {profile.competitors}"

    results = await asyncio.gather(*[
        _run_persona_agent(persona, offer_summary)
        for persona in _DEBATE_PERSONAS
    ])
    successful = [r for r in results if r is not None]

    for i, obj in enumerate(successful):
        objection = DebateObjection(
            debate_id=debate.id,
            objection_text=obj["objection"],
            objection_source=obj["source"],
            severity=obj["severity"],
            proposed_solution=obj.get("proposed_solution") or None,
            order_index=i,
        )
        session.add(objection)
    session.commit()

    if not successful:
        debate.status = "completed"
        debate.completed_at = datetime.now(timezone.utc)
        debate.final_verdict = "approved"
        debate.arbiter_summary = "No se generaron objeciones — oferta aprobada por defecto."
        session.add(debate)
        offer.status = "validated"
        session.add(offer)
        session.commit()
        return debate

    arbiter_result = await _run_arbiter(offer_summary, successful)

    if arbiter_result:
        resolutions = arbiter_result.get("resolutions", [])
        objection_rows = session.query(DebateObjection).filter(
            DebateObjection.debate_id == debate.id
        ).order_by(DebateObjection.order_index).all()

        for res in resolutions:
            idx = res.get("index", 0) - 1
            if 0 <= idx < len(objection_rows):
                row = objection_rows[idx]
                row.resolution_status = res.get("status", "resolved")
                row.resolved_text = res.get("text", "")
                session.add(row)

        verdict = arbiter_result.get("verdict", "needs_revision")
        debate.final_verdict = verdict
        debate.arbiter_summary = arbiter_result.get("summary", "")
        action_plan = arbiter_result.get("action_plan")
        if action_plan:
            debate.action_plan_json = json.dumps(action_plan, ensure_ascii=False)
        offer.status = "validated" if verdict == "approved" else "rejected"
    else:
        debate.final_verdict = "needs_revision"
        debate.arbiter_summary = "El arbitro no pudo procesar las objeciones. Revise manualmente."
        offer.status = "rejected"

    debate.status = "completed"
    debate.completed_at = datetime.now(timezone.utc)
    session.add(debate)
    session.add(offer)
    session.commit()
    session.refresh(debate)
    return debate
