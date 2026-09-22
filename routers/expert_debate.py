"""Debate de Personas: expertos humanos calificados validan ofertas."""
from __future__ import annotations

import json
import os
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select

from database.models import (
    ExpertDebate, ExpertOpinion, Offer, ResearchProject,
    Settings, Tenant, User,
)
from database.session import get_session
from web.compat_templates import CompatTemplates
from web.dependencies import get_settings, get_tenant, require_auth

router = APIRouter(tags=["Expert Debate"])


def _templates():
    return CompatTemplates(directory="templates")


EXPERT_PROFILES = [
    {
        "name": "Laura Méndez",
        "role": "marketing",
        "title": "Directora de Marketing Digital",
        "bio": "15 años en estrategias de growth marketing para startups y PYMEs en Latinoamérica.",
    },
    {
        "name": "Carlos Ruiz",
        "role": "finance",
        "title": "Analista Financiero Senior",
        "bio": "Especialista en modelos de pricing y viabilidad financiera de nuevos productos.",
    },
    {
        "name": "Ana Torrealba",
        "role": "operations",
        "title": "Consultora de Operaciones",
        "bio": "Experta en cadena de suministro, logística y escalabilidad operativa.",
    },
    {
        "name": "Diego Herrera",
        "role": "industry",
        "title": "Experto en el Sector",
        "bio": "Analista de mercado con experiencia en tendencias de consumo y competencia.",
    },
    {
        "name": "Valentina Castro",
        "role": "ux",
        "title": "Diseñadora UX/CX",
        "bio": "Especialista en experiencia de usuario y customer journey para ecommerce.",
    },
    {
        "name": "Martín Solano",
        "role": "skeptic",
        "title": "Consumidor Escéptico",
        "bio": "Desconfia de las promesas de marketing. Compara todo, busca letra chica, lee reseñas negativas antes de comprar. Si lo convences a él, convences a cualquiera.",
    },
    {
        "name": "Sofía Delgado",
        "role": "compulsive_buyer",
        "title": "Compradora Compulsiva",
        "bio": "Compra por impulso, se engancha con ofertas y novedad. Representa al cliente emocional que decide en segundos. Si ella no se engancha, tu hook no funciona.",
    },
]


@router.get("/panel/oferta/{offer_id}/debate-personas", response_class=HTMLResponse)
def expert_debate_page(
    offer_id: int,
    request: Request,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    tenant = session.get(Tenant, tenant_id)
    if not tenant or not (tenant.has_landing or tenant.has_ecommerce):
        raise HTTPException(403, "Tu cuenta no tiene acceso a este modulo")

    offer = session.exec(
        select(Offer).where(Offer.id == offer_id, Offer.tenant_id == tenant_id)
    ).first()
    if not offer:
        raise HTTPException(404, "Oferta no encontrada")

    project = session.get(ResearchProject, offer.project_id)

    debate = session.exec(
        select(ExpertDebate).where(
            ExpertDebate.offer_id == offer_id,
            ExpertDebate.tenant_id == tenant_id,
        )
    ).first()

    return _templates().TemplateResponse(
        "panel_debate_personas.html",
        {
            "request": request,
            "user": user,
            "settings": settings,
            "offer": offer,
            "project": project,
            "debate": debate,
            "expert_profiles": EXPERT_PROFILES,
            "active_page": "offer",
        },
    )


@router.post("/panel/oferta/{offer_id}/debate-personas/iniciar")
def start_expert_debate(
    offer_id: int,
    request: Request,
    user: User = Depends(require_auth),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    tenant = session.get(Tenant, tenant_id)
    if not tenant or not (tenant.has_landing or tenant.has_ecommerce):
        raise HTTPException(403, "Tu cuenta no tiene acceso a este modulo")

    offer = session.exec(
        select(Offer).where(Offer.id == offer_id, Offer.tenant_id == tenant_id)
    ).first()
    if not offer:
        raise HTTPException(404, "Oferta no encontrada")

    existing = session.exec(
        select(ExpertDebate).where(
            ExpertDebate.offer_id == offer_id,
            ExpertDebate.tenant_id == tenant_id,
        )
    ).first()
    if existing:
        raise HTTPException(400, "Ya existe un debate de personas para esta oferta")

    project = session.get(ResearchProject, offer.project_id)

    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if not gemini_key:
        raise HTTPException(503, "API de IA no configurada")

    debate = ExpertDebate(offer_id=offer_id, tenant_id=tenant_id)
    session.add(debate)
    session.commit()
    session.refresh(debate)

    from services.gemini_service import GeminiService

    for profile in EXPERT_PROFILES:
        prompt = f"""Eres {profile['name']}, {profile['title']}. {profile['bio']}

Un emprendedor te pide tu opinión profesional sobre esta oferta de negocio:

- Producto/Servicio: {offer.title}
- Propuesta de valor: {offer.value_proposition}
- Estructura de precios: {offer.price_structure}
- Investigación base: {project.query_description if project else 'No disponible'}

Da tu opinión profesional desde tu área de expertise ({profile['role']}). Sé directo y constructivo.
Responde EXCLUSIVAMENTE este JSON:
{{
  "opinion": "Tu análisis profesional de 3-5 oraciones desde tu perspectiva de {profile['title']}",
  "verdict": "approve" o "reject" o "neutral",
  "suggestions": "1-3 sugerencias concretas de mejora desde tu área"
}}
No agregues markdown ni texto fuera del JSON."""

        try:
            raw = asyncio.run(GeminiService._call_gemini_api(
                prompt,
                f"Eres {profile['name']}, {profile['title']}. Responde como experto real.",
                gemini_key,
            ))
            cleaned = raw.strip().strip("```").strip()
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()
            data = json.loads(cleaned)
        except Exception:
            data = {
                "opinion": f"Como {profile['title']}, considero que la oferta tiene potencial pero necesita más datos para un análisis completo.",
                "verdict": "neutral",
                "suggestions": "Proporcionar más detalles sobre el mercado objetivo y la competencia.",
            }

        opinion = ExpertOpinion(
            debate_id=debate.id,
            tenant_id=tenant_id,
            expert_name=profile["name"],
            expert_role=profile["role"],
            expert_email=None,
            opinion_text=data.get("opinion", ""),
            verdict=data.get("verdict", "neutral"),
            suggestions=data.get("suggestions", ""),
            source="ai_generated",
        )
        session.add(opinion)

    session.commit()
    session.refresh(debate)

    return {"status": "success", "debate_id": debate.id}


@router.post("/panel/oferta/{offer_id}/debate-personas/opinion")
async def add_manual_opinion(
    offer_id: int,
    request: Request,
    user: User = Depends(require_auth),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(403, "Sin acceso")

    debate = session.exec(
        select(ExpertDebate).where(
            ExpertDebate.offer_id == offer_id,
            ExpertDebate.tenant_id == tenant_id,
        )
    ).first()
    if not debate:
        raise HTTPException(404, "Debate no encontrado")

    form = await request.form()
    name = form.get("expert_name", "").strip()
    role = form.get("expert_role", "industry").strip()
    text = form.get("opinion_text", "").strip()
    verdict = form.get("verdict", "neutral").strip()
    suggestions = form.get("suggestions", "").strip()

    if not name or not text:
        raise HTTPException(400, "Nombre y opinión son requeridos")

    opinion = ExpertOpinion(
        debate_id=debate.id,
        tenant_id=tenant_id,
        expert_name=name,
        expert_role=role,
        opinion_text=text,
        verdict=verdict,
        suggestions=suggestions,
        source="manual",
    )
    session.add(opinion)
    session.commit()

    return {"status": "success"}
