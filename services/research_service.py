from __future__ import annotations

import logging
import os
import time
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
    keepa_key = os.getenv("KEEPA_API_KEY", "")
    if keepa_key:
        from services.research_providers.keepa_provider import KeepaProvider
        return KeepaProvider(keepa_key)
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if gemini_key:
        from services.research_providers.gemini_provider import GeminiMarketProvider
        return GeminiMarketProvider(gemini_key)
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
    provider = _get_provider()
    project.status = "researching"
    session.add(project)
    session.commit()

    try:
        t0 = time.monotonic()
        raw_listings = await provider.search_products(project.query_description, project.reference_url)
        raw_demand = await provider.estimate_demand(project.query_description)
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info("Research completed in %dms via %s", elapsed_ms, type(provider).__name__)
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
