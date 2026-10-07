"""Debate de Personas: expertos humanos calificados validan ofertas con debate en tiempo real."""
from __future__ import annotations

import json
import os
import asyncio

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlmodel import Session, select

from database.models import (
    ExpertDebate, ExpertOpinion, Offer, ResearchProject,
    Settings, Tenant, User,
)
from database.session import get_session
from services.entitlements import can_use_module, get_blocked_message
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


def _generate_single_opinion(profile: dict, offer, project, gemini_key: str) -> dict:
    """Generate one expert opinion via Gemini. Returns parsed dict."""
    from services.gemini_service import GeminiService

    previous_opinions_text = ""
    if hasattr(offer, "_debate_opinions_so_far") and offer._debate_opinions_so_far:
        parts = []
        for prev in offer._debate_opinions_so_far:
            parts.append(f"- {prev['name']} ({prev['title']}): {prev['opinion'][:200]}")
        previous_opinions_text = "\n\nOPINIONES PREVIAS DE OTROS EXPERTOS (puedes referenciarlas, rebatirlas o apoyarlas):\n" + "\n".join(parts)

    prompt = f"""Eres {profile['name']}, {profile['title']}. {profile['bio']}

Un emprendedor te pide tu opinión profesional sobre esta oferta de negocio:

- Producto/Servicio: {offer.title}
- Propuesta de valor: {offer.value_proposition}
- Estructura de precios: {offer.price_structure}
- Investigación base: {project.query_description if project else 'No disponible'}{previous_opinions_text}

Da tu opinión profesional desde tu área de expertise ({profile['role']}). Sé directo y constructivo.
{"Si otros expertos ya opinaron, puedes referenciar sus puntos para crear un debate real. Puedes estar de acuerdo, en desacuerdo, o añadir matices." if previous_opinions_text else ""}
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
            f"Eres {profile['name']}, {profile['title']}. Responde como experto real en un debate profesional.",
            gemini_key,
        ))
        cleaned = raw.strip().strip("```").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
        return json.loads(cleaned)
    except Exception:
        return {
            "opinion": f"Como {profile['title']}, considero que la oferta tiene potencial pero necesita más datos para un análisis completo.",
            "verdict": "neutral",
            "suggestions": "Proporcionar más detalles sobre el mercado objetivo y la competencia.",
        }


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
    if not tenant or not can_use_module(tenant, "expert_debate"):
        raise HTTPException(403, get_blocked_message("expert_debate"))

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
    """Create debate record and return immediately — opinions generated via /siguiente polling."""
    tenant = session.get(Tenant, tenant_id)
    if not tenant or not can_use_module(tenant, "expert_debate"):
        raise HTTPException(403, get_blocked_message("expert_debate"))

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

    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if not gemini_key:
        raise HTTPException(503, "API de IA no configurada")

    debate = ExpertDebate(offer_id=offer_id, tenant_id=tenant_id, status="in_progress")
    session.add(debate)
    session.commit()
    session.refresh(debate)

    return {
        "status": "started",
        "debate_id": debate.id,
        "total_experts": len(EXPERT_PROFILES),
    }


@router.get("/panel/oferta/{offer_id}/debate-personas/estado")
def debate_estado(
    offer_id: int,
    request: Request,
    user: User = Depends(require_auth),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    """Return current debate state: opinions generated so far + who's next."""
    debate = session.exec(
        select(ExpertDebate).where(
            ExpertDebate.offer_id == offer_id,
            ExpertDebate.tenant_id == tenant_id,
        )
    ).first()
    if not debate:
        raise HTTPException(404, "Debate no encontrado")

    opinions = []
    for op in debate.opinions:
        opinions.append({
            "id": op.id,
            "expert_name": op.expert_name,
            "expert_role": op.expert_role,
            "opinion_text": op.opinion_text,
            "verdict": op.verdict,
            "suggestions": op.suggestions,
            "source": op.source,
        })

    generated_roles = {op.expert_role for op in debate.opinions if op.source == "ai_generated"}
    next_expert = None
    for profile in EXPERT_PROFILES:
        if profile["role"] not in generated_roles:
            next_expert = {"name": profile["name"], "role": profile["role"], "title": profile["title"]}
            break

    return {
        "status": debate.status,
        "debate_id": debate.id,
        "opinions": opinions,
        "generated_count": len([o for o in opinions if o["source"] == "ai_generated"]),
        "total_experts": len(EXPERT_PROFILES),
        "next_expert": next_expert,
        "is_complete": debate.status == "completed",
    }


@router.post("/panel/oferta/{offer_id}/debate-personas/siguiente")
def generate_next_opinion(
    offer_id: int,
    request: Request,
    user: User = Depends(require_auth),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    """Generate the next expert's opinion. Called sequentially by the frontend."""
    debate = session.exec(
        select(ExpertDebate).where(
            ExpertDebate.offer_id == offer_id,
            ExpertDebate.tenant_id == tenant_id,
        )
    ).first()
    if not debate:
        raise HTTPException(404, "Debate no encontrado")
    if debate.status == "completed":
        return {"status": "completed", "opinion": None}

    offer = session.exec(
        select(Offer).where(Offer.id == offer_id, Offer.tenant_id == tenant_id)
    ).first()
    if not offer:
        raise HTTPException(404, "Oferta no encontrada")

    project = session.get(ResearchProject, offer.project_id)

    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if not gemini_key:
        raise HTTPException(503, "API de IA no configurada")

    generated_roles = {op.expert_role for op in debate.opinions if op.source == "ai_generated"}
    next_profile = None
    for profile in EXPERT_PROFILES:
        if profile["role"] not in generated_roles:
            next_profile = profile
            break

    if not next_profile:
        debate.status = "completed"
        session.add(debate)
        session.commit()
        return {"status": "completed", "opinion": None}

    # Pass previous opinions so the expert can reference them
    offer._debate_opinions_so_far = [
        {
            "name": op.expert_name,
            "title": next(
                (p["title"] for p in EXPERT_PROFILES if p["role"] == op.expert_role),
                op.expert_role,
            ),
            "opinion": op.opinion_text,
        }
        for op in debate.opinions
        if op.source == "ai_generated"
    ]

    data = _generate_single_opinion(next_profile, offer, project, gemini_key)

    opinion = ExpertOpinion(
        debate_id=debate.id,
        tenant_id=tenant_id,
        expert_name=next_profile["name"],
        expert_role=next_profile["role"],
        expert_email=None,
        opinion_text=data.get("opinion", ""),
        verdict=data.get("verdict", "neutral"),
        suggestions=data.get("suggestions", ""),
        source="ai_generated",
    )
    session.add(opinion)

    remaining = len(EXPERT_PROFILES) - len(generated_roles) - 1
    if remaining <= 0:
        debate.status = "completed"
        session.add(debate)

    session.commit()

    return {
        "status": "generating" if remaining > 0 else "completed",
        "opinion": {
            "expert_name": opinion.expert_name,
            "expert_role": opinion.expert_role,
            "opinion_text": opinion.opinion_text,
            "verdict": opinion.verdict,
            "suggestions": opinion.suggestions,
        },
        "generated_count": len(generated_roles) + 1,
        "total_experts": len(EXPERT_PROFILES),
    }


@router.post("/panel/oferta/{offer_id}/debate-personas/opinion")
def add_manual_opinion(
    offer_id: int,
    user: User = Depends(require_auth),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
    expert_name: str = Form(""),
    expert_role: str = Form("industry"),
    opinion_text: str = Form(""),
    verdict: str = Form("neutral"),
    suggestions: str = Form(""),
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

    name = expert_name.strip()
    role = expert_role.strip()
    text = opinion_text.strip()
    verdict = verdict.strip()
    suggestions = suggestions.strip()

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
