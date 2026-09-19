"""services/competitor_service.py — Declaración y análisis de competencia por el usuario (Etapa 5 PRD)"""
from __future__ import annotations

import json
import logging
from typing import Optional

from sqlmodel import Session, select

from database.models import CompetitorAnalysis, ResearchProject

logger = logging.getLogger("competitor_service")


def add_competitor(
    session: Session,
    project_id: int,
    tenant_id: int,
    url: str,
    notes: Optional[str] = None,
) -> CompetitorAnalysis:
    """Valida ownership del ResearchProject y crea fila CompetitorAnalysis."""
    project = session.exec(
        select(ResearchProject).where(
            ResearchProject.id == project_id,
            ResearchProject.tenant_id == tenant_id,
        )
    ).first()
    if not project:
        raise ValueError(f"Proyecto {project_id} no encontrado o no pertenece al tenant {tenant_id}")

    initial_json = json.dumps({"notes": notes}) if notes else None

    competitor = CompetitorAnalysis(
        project_id=project.id,
        url=url.strip(),
        analysis_json=initial_json,
        user_confirmed=False,
    )
    session.add(competitor)
    session.commit()
    session.refresh(competitor)
    return competitor


def list_competitors(session: Session, project_id: int, tenant_id: int) -> list[CompetitorAnalysis]:
    """Lista competidores del proyecto validando tenant."""
    project = session.exec(
        select(ResearchProject).where(
            ResearchProject.id == project_id,
            ResearchProject.tenant_id == tenant_id,
        )
    ).first()
    if not project:
        return []

    return list(session.exec(
        select(CompetitorAnalysis)
        .where(CompetitorAnalysis.project_id == project_id)
        .order_by(CompetitorAnalysis.created_at.asc())
    ).all())


def remove_competitor(session: Session, competitor_id: int, tenant_id: int) -> bool:
    """Valida ownership vía el project relacionado antes de borrar."""
    stmt = (
        select(CompetitorAnalysis)
        .join(ResearchProject, CompetitorAnalysis.project_id == ResearchProject.id)
        .where(
            CompetitorAnalysis.id == competitor_id,
            ResearchProject.tenant_id == tenant_id,
        )
    )
    competitor = session.exec(stmt).first()
    if not competitor:
        return False

    session.delete(competitor)
    session.commit()
    return True


async def run_competitor_analysis(session: Session, project: ResearchProject) -> None:
    """
    Para cada CompetitorAnalysis pendiente de análisis del proyecto,
    llama a ai_gateway en cascada (claude -> gemini -> qwen).
    El prompt exige citar explícitamente el nombre/URL del competidor en cada punto (PRD P0 #4).
    """
    from services.ai.contracts import AIMessage, AIRequest
    from services.ai.gateway import ai_gateway

    competitors = session.exec(
        select(CompetitorAnalysis).where(CompetitorAnalysis.project_id == project.id)
    ).all()

    for comp in competitors:
        # Si ya tiene value_proposition y análisis completo, no re-ejecutar
        if comp.value_proposition and comp.analysis_json and '"analysis_completed": true' in comp.analysis_json:
            continue

        existing_notes = ""
        if comp.analysis_json:
            try:
                data = json.loads(comp.analysis_json)
                existing_notes = data.get("notes") or ""
            except Exception:
                pass

        system_prompt = (
            "Sos un analista senior de inteligencia competitiva y estrategia de mercado. "
            "Tu tarea es analizar en profundidad un competidor declarado por el usuario contra su idea/producto. "
            "REGLA OBLIGATORIA: En cada campo (value_proposition, price_info, guarantees, objections_addressed), "
            f"DEBES citar explícitamente el competidor por su URL o nombre ('{comp.url}') para contrastar con precisión.\n"
            "Responde ÚNICAMENTE con un objeto JSON válido con estas claves exactas:\n"
            "{\n"
            f'  "value_proposition": "Propuesta de valor detectada para {comp.url} y cómo se compara contra la propuesta del usuario.",\n'
            f'  "price_info": "Estructura de precios o nivel de precios estimado de {comp.url} vs el proyecto.",\n'
            f'  "guarantees": "Garantías, políticas de devolución o soporte ofrecidos por {comp.url}.",\n'
            f'  "objections_addressed": "Qué objeciones de clientes resuelve bien {comp.url} y qué vacíos deja libres."\n'
            "}\n"
            "No agregues texto ni explicaciones fuera del JSON."
        )

        user_prompt = (
            f"Proyecto/Idea del usuario:\n"
            f"- Descripción: {project.query_description}\n"
            f"- Tipo: {project.project_type}\n"
            f"- Precio/costo base: {project.factory_price or 'No especificado'}\n\n"
            f"Competidor declarado a analizar:\n"
            f"- URL: {comp.url}\n"
            f"- Notas del usuario: {existing_notes or 'Sin notas adicionales'}\n\n"
            f"Realiza el análisis comparativo citando siempre '{comp.url}'."
        )

        request = AIRequest(
            task="competitor_analysis",
            messages=[AIMessage(role="user", content=user_prompt)],
            system_prompt=system_prompt,
            provider="claude",
            max_tokens=1024,
            timeout=30.0,
        )

        parsed = None
        raw_response = ""
        for provider in ("claude", "gemini", "qwen"):
            try:
                request.provider = provider
                if provider == "qwen":
                    request.model = "qwen-plus"
                response = await ai_gateway.generate(request)
                raw_response = response.content.strip()
                clean = raw_response
                if clean.startswith("```"):
                    clean = clean.strip("`")
                    if clean.lower().startswith("json"):
                        clean = clean[4:]
                    clean = clean.strip()
                parsed = json.loads(clean)
                break
            except Exception as exc:
                logger.warning("Fallo proveedor %s en análisis de competidor %s: %s", provider, comp.url, exc)
                parsed = None

        if parsed:
            comp.value_proposition = str(parsed.get("value_proposition", ""))
            comp.price_info = str(parsed.get("price_info", ""))
            comp.guarantees = str(parsed.get("guarantees", ""))
            comp.objections_addressed = str(parsed.get("objections_addressed", ""))
            payload_to_store = {
                "url": comp.url,
                "notes": existing_notes,
                "analysis": parsed,
                "raw_response": raw_response,
                "analysis_completed": True,
            }
            comp.analysis_json = json.dumps(payload_to_store, ensure_ascii=False)
            session.add(comp)
            session.commit()
            session.refresh(comp)
        else:
            logger.error("No se pudo obtener análisis de IA para competidor %s", comp.url)


def confirm_competitor(session: Session, competitor_id: int, tenant_id: int) -> Optional[CompetitorAnalysis]:
    """Confirma que el competidor analizado es válido (user_confirmed=True)."""
    stmt = (
        select(CompetitorAnalysis)
        .join(ResearchProject, CompetitorAnalysis.project_id == ResearchProject.id)
        .where(
            CompetitorAnalysis.id == competitor_id,
            ResearchProject.tenant_id == tenant_id,
        )
    )
    competitor = session.exec(stmt).first()
    if not competitor:
        return None

    competitor.user_confirmed = True
    session.add(competitor)
    session.commit()
    session.refresh(competitor)
    return competitor
