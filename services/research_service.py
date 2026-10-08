from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlmodel import Session, select

from database.models import (
    CompetitorAnalysis,
    ResearchDemand,
    ResearchListing,
    ResearchProject,
)
from services.research_providers.base import ProductDataProvider

logger = logging.getLogger("research_service")


def _get_provider() -> ProductDataProvider:
    """Retorna el mejor provider disponible (para compatibilidad)."""
    providers = _get_providers()
    return providers[0] if providers else _fallback_provider()


def _get_providers() -> list[ProductDataProvider]:
    """Retorna todos los providers configurados, en orden de prioridad."""
    providers: list[ProductDataProvider] = []

    keepa_key = os.getenv("KEEPA_API_KEY", "")
    if keepa_key:
        from services.research_providers.keepa_provider import KeepaProvider
        try:
            providers.append(KeepaProvider(keepa_key))
        except Exception:
            pass

    meli_site = os.getenv("MELI_SITE_ID", "MLA")
    from services.research_providers.meli_provider import MeliProvider
    providers.append(MeliProvider(meli_site))

    from services.research_providers.aliexpress_provider import AliExpressProvider
    providers.append(AliExpressProvider())

    from services.research_providers.reddit_provider import RedditProvider
    providers.append(RedditProvider())

    youtube_key = os.getenv("YOUTUBE_API_KEY", "")
    if youtube_key:
        from services.research_providers.youtube_provider import YouTubeProvider
        try:
            providers.append(YouTubeProvider(youtube_key))
        except Exception:
            pass

    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if gemini_key:
        from services.research_providers.gemini_provider import GeminiMarketProvider
        providers.append(GeminiMarketProvider(gemini_key))

    if not providers:
        providers.append(_fallback_provider())

    return providers


def _fallback_provider() -> ProductDataProvider:
    from services.research_providers.mock_provider import MockProvider
    return MockProvider()


def create_project(
    session: Session,
    tenant_id: int,
    user_id: int,
    project_type: str,
    query_description: str,
    reference_url: Optional[str] = None,
    factory_price: Optional[Decimal] = None,
) -> ResearchProject:
    project = ResearchProject(
        tenant_id=tenant_id,
        user_id=user_id,
        project_type=project_type,
        query_description=query_description,
        reference_url=reference_url,
        factory_price=factory_price,
        status="draft",
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


async def run_product_search(session: Session, project: ResearchProject) -> list[ResearchListing]:
    providers = _get_providers()
    project.status = "researching"
    session.add(project)
    session.commit()

    try:
        t0 = time.monotonic()
        raw_listings: list = []
        raw_demand = None
        seen_titles: set[str] = set()

        for provider in providers:
            try:
                results = await provider.search_products(
                    project.query_description, project.reference_url,
                )
                for listing in results:
                    key = listing.title.lower().strip()
                    if key not in seen_titles:
                        seen_titles.add(key)
                        raw_listings.append(listing)

                if raw_demand is None:
                    raw_demand = await provider.estimate_demand(project.query_description)
            except Exception as prov_exc:
                logger.warning(
                    "Provider %s falló: %s", type(provider).__name__, prov_exc,
                )
                continue

        if raw_demand is None:
            from services.research_providers.base import DemandEstimate
            raw_demand = DemandEstimate(
                confidence_level="bajo",
                source_description="Sin datos de demanda disponibles",
            )

        if not raw_listings:
            fallback = _fallback_provider()
            raw_listings = await fallback.search_products(
                project.query_description, project.reference_url,
            )
            if raw_demand.confidence_level == "bajo" and raw_demand.estimated_monthly_volume is None:
                raw_demand = await fallback.estimate_demand(project.query_description)

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        providers_used = ", ".join(type(p).__name__ for p in providers)
        logger.info(
            "Research completed in %dms via [%s] — %d listings",
            elapsed_ms, providers_used, len(raw_listings),
        )
    except Exception as exc:
        project.status = "error"
        session.add(project)
        session.commit()
        raise RuntimeError(f"Error en búsqueda: {exc}") from exc

    # Limpiar resultados y demanda previos en caso de re-análisis
    existing_listings = session.exec(
        select(ResearchListing).where(ResearchListing.project_id == project.id)
    ).all()
    for el in existing_listings:
        session.delete(el)
    existing_demand = session.exec(
        select(ResearchDemand).where(ResearchDemand.project_id == project.id)
    ).first()
    if existing_demand:
        session.delete(existing_demand)
    session.flush()

    now = datetime.now(timezone.utc)
    db_listings: list[ResearchListing] = []
    for rl in raw_listings:
        listing = ResearchListing(
            project_id=project.id,
            source=rl.source,
            title=rl.title,
            price=rl.price,
            currency=rl.currency,
            url=rl.url,
            rating=rl.rating,
            review_count=rl.review_count,
            is_demo=rl.is_demo,
            source_date=now,
        )
        session.add(listing)
        db_listings.append(listing)

    demand = ResearchDemand(
        project_id=project.id,
        confidence_level=raw_demand.confidence_level,
        estimated_monthly_volume=raw_demand.estimated_monthly_volume,
        source_description=raw_demand.source_description,
        notes=raw_demand.notes,
    )
    session.add(demand)

    project.status = "completed"
    session.add(project)
    session.commit()

    for listing in db_listings:
        session.refresh(listing)
    return db_listings


def get_project_with_results(session: Session, project_id: int, tenant_id: int) -> Optional[ResearchProject]:
    project = session.exec(
        select(ResearchProject).where(
            ResearchProject.id == project_id,
            ResearchProject.tenant_id == tenant_id,
        )
    ).first()
    if not project:
        return None
    _ = project.listings
    _ = project.demand
    _ = project.competitors
    return project


def list_projects(session: Session, tenant_id: int) -> list[ResearchProject]:
    return list(session.exec(
        select(ResearchProject)
        .where(ResearchProject.tenant_id == tenant_id)
        .order_by(ResearchProject.created_at.desc())
    ).all())


async def verify_listing_with_llms(
    session: Session,
    listing: ResearchListing,
) -> bool:
    """Verifica que el dato del listing aparezca en la fuente usando 2 LLMs.

    Si ambos confirman que el dato está en la fuente, marca verified=True.
    Sin fuente URL, no se puede verificar.
    """
    if not listing.url or listing.is_demo:
        return False

    claim = f"Producto: {listing.title}"
    if listing.price is not None:
        claim += f", Precio: {listing.price} {listing.currency}"

    prompt = (
        f"Dato a verificar: {claim}\n"
        f"Fuente: {listing.source} ({listing.url})\n\n"
        "¿Es razonable que este dato aparezca en esa fuente? "
        "Responde SOLO 'si' o 'no'."
    )

    confirmations = []
    llm_results = {}

    from services.ai_gateway_service import ai_gateway_service

    for provider_name in ("gemini", "qwen"):
        try:
            result = await ai_gateway_service.call_llm_simple(prompt, provider=provider_name)
            answer = (result or "").strip().lower()
            confirmed = answer.startswith("si") or answer.startswith("sí") or answer == "yes"
            confirmations.append(confirmed)
            llm_results[provider_name] = {"answer": answer, "confirmed": confirmed}
        except Exception as exc:
            logger.warning("Verificación con %s falló: %s", provider_name, exc)
            llm_results[provider_name] = {"error": str(exc), "confirmed": False}

    verified = len(confirmations) >= 2 and all(confirmations)

    listing.verified = verified
    listing.verification_details = json.dumps(llm_results)
    session.add(listing)
    session.commit()

    return verified


async def verify_project_listings(session: Session, project: ResearchProject) -> int:
    """Verifica todos los listings de un proyecto. Retorna cuántos fueron verificados."""
    listings = session.exec(
        select(ResearchListing).where(
            ResearchListing.project_id == project.id,
            ResearchListing.is_demo == False,
        )
    ).all()

    verified_count = 0
    for listing in listings:
        if await verify_listing_with_llms(session, listing):
            verified_count += 1

    return verified_count
