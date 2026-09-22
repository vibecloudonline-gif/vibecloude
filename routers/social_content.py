"""Sugerencias de contenido para redes sociales basado en la investigación del emprendedor."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select

from database.models import Settings, Tenant, User
from database.session import get_session
from web.compat_templates import CompatTemplates
from web.dependencies import get_settings, get_tenant, require_auth

router = APIRouter(tags=["Social Content"])


def _templates():
    return CompatTemplates(directory="templates")


@router.get("/panel/contenido-redes", response_class=HTMLResponse)
def social_content_page(
    request: Request,
    user: User = Depends(require_auth),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    tenant = session.get(Tenant, tenant_id)
    if not tenant or not (tenant.has_landing or tenant.has_ecommerce):
        raise HTTPException(403, "Tu cuenta no tiene acceso a este modulo")

    from database.models import ResearchProject, Offer
    projects = session.exec(
        select(ResearchProject).where(ResearchProject.tenant_id == tenant_id)
        .order_by(ResearchProject.id.desc())
    ).all()

    completed_projects = []
    for p in projects:
        offer = session.exec(
            select(Offer).where(Offer.project_id == p.id)
        ).first()
        if offer and offer.debate:
            completed_projects.append({
                "project": p,
                "offer": offer,
                "debate": offer.debate,
            })

    return _templates().TemplateResponse(
        "panel_contenido_redes.html",
        {
            "request": request,
            "user": user,
            "settings": settings,
            "completed_projects": completed_projects,
            "active_page": "social_content",
        },
    )


@router.post("/panel/contenido-redes/{offer_id}/generar")
def generate_social_content(
    offer_id: int,
    request: Request,
    user: User = Depends(require_auth),
    session: Session = Depends(get_session),
    tenant_id: int = Depends(get_tenant),
):
    tenant = session.get(Tenant, tenant_id)
    if not tenant or not (tenant.has_landing or tenant.has_ecommerce):
        raise HTTPException(403, "Tu cuenta no tiene acceso a este modulo")

    from database.models import Offer
    offer = session.exec(
        select(Offer).where(Offer.id == offer_id, Offer.tenant_id == tenant_id)
    ).first()
    if not offer:
        raise HTTPException(404, "Oferta no encontrada")

    import os, json
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if not gemini_key:
        raise HTTPException(503, "API de IA no configurada")

    debate = offer.debate
    debate_summary = ""
    if debate:
        debate_summary = f"Veredicto del debate: {debate.final_verdict}. Resumen: {debate.arbiter_summary or ''}"

    prompt = f"""Eres un experto en marketing digital y contenido para redes sociales.

Un emprendedor tiene esta oferta validada:
- Título: {offer.title or 'Sin título'}
- Propuesta de valor: {offer.value_proposition or ''}
- Precio: {offer.price_structure or ''}
{debate_summary}

Genera contenido listo para publicar en redes sociales. Responde EXCLUSIVAMENTE este JSON:
{{
  "instagram_posts": [
    {{"caption": "texto del post con hashtags", "visual_idea": "descripcion de la imagen/video sugerido"}},
    {{"caption": "...", "visual_idea": "..."}}
  ],
  "tiktok_ideas": [
    {{"hook": "primeros 3 segundos", "script": "guion corto del video", "hashtags": "#tag1 #tag2"}},
    {{"hook": "...", "script": "...", "hashtags": "..."}}
  ],
  "twitter_threads": [
    {{"tweets": ["tweet 1", "tweet 2", "tweet 3"]}}
  ],
  "content_calendar": [
    {{"day": "Lunes", "platform": "Instagram", "type": "Carousel", "topic": "tema"}},
    {{"day": "Miercoles", "platform": "TikTok", "type": "Video corto", "topic": "tema"}},
    {{"day": "Viernes", "platform": "Twitter", "type": "Thread", "topic": "tema"}}
  ]
}}
No agregues markdown ni texto fuera del JSON."""

    import asyncio
    from services.gemini_service import GeminiService
    try:
        raw = asyncio.run(GeminiService._call_gemini_api(
            prompt, "Eres un experto en marketing digital.", gemini_key
        ))
        cleaned = raw.strip().strip("")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
        content = json.loads(cleaned)
    except Exception as exc:
        raise HTTPException(500, f"Error generando contenido: {exc}")

    return {"status": "success", "content": content}
