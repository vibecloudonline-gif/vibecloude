"""YouTube Data API v3 provider — reviews en video y tendencias."""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

import httpx

from services.research_providers.base import (
    DemandEstimate,
    ProductDataProvider,
    ProductListing,
    ProviderNotConfigured,
)

logger = logging.getLogger("research.youtube")

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


class YouTubeProvider(ProductDataProvider):

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ProviderNotConfigured("YOUTUBE_API_KEY no configurada")
        self.api_key = api_key

    async def search_products(
        self, query: str, reference_url: Optional[str] = None
    ) -> list[ProductListing]:
        search_params = {
            "key": self.api_key,
            "q": f"{query} review unboxing opinión",
            "part": "snippet",
            "type": "video",
            "maxResults": 10,
            "order": "relevance",
            "relevanceLanguage": "es",
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(SEARCH_URL, params=search_params)
                resp.raise_for_status()
                search_data = resp.json()

            items = search_data.get("items", [])
            if not items:
                logger.info("YouTube search sin resultados para: %s", query)
                return []

            video_ids = [
                item["id"]["videoId"]
                for item in items
                if item.get("id", {}).get("videoId")
            ]

            if not video_ids:
                return []

            stats = await self._get_video_stats(video_ids)

            listings: list[ProductListing] = []
            for item in items:
                video_id = item.get("id", {}).get("videoId", "")
                snippet = item.get("snippet", {})
                title = snippet.get("title", "")
                channel = snippet.get("channelTitle", "")

                if not title or not video_id:
                    continue

                video_stats = stats.get(video_id, {})
                view_count = int(video_stats.get("viewCount", 0))
                like_count = int(video_stats.get("likeCount", 0))

                listings.append(ProductListing(
                    source=f"YouTube ({channel})",
                    title=title[:200],
                    price=None,
                    currency="USD",
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    rating=None,
                    review_count=view_count,
                    is_demo=False,
                ))

            return listings

        except httpx.HTTPStatusError as exc:
            logger.warning("YouTube search HTTP %d: %s", exc.response.status_code, exc)
            return []
        except Exception as exc:
            logger.warning("YouTube search error: %s", exc)
            return []

    async def _get_video_stats(self, video_ids: list[str]) -> dict:
        params = {
            "key": self.api_key,
            "id": ",".join(video_ids),
            "part": "statistics",
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(VIDEOS_URL, params=params)
                resp.raise_for_status()
                data = resp.json()

            return {
                item["id"]: item.get("statistics", {})
                for item in data.get("items", [])
            }
        except Exception as exc:
            logger.warning("YouTube stats error: %s", exc)
            return {}

    async def estimate_demand(self, query: str) -> DemandEstimate:
        try:
            listings = await self.search_products(query)
            if not listings:
                return DemandEstimate(
                    confidence_level="bajo",
                    estimated_monthly_volume=None,
                    source_description="YouTube — sin resultados",
                    notes=f"No se encontraron videos sobre '{query}'.",
                )

            total_views = sum(p.review_count or 0 for p in listings)
            channels = set(
                p.source.replace("YouTube (", "").rstrip(")")
                for p in listings
            )

            if total_views > 1_000_000:
                confidence = "alto"
            elif total_views > 100_000:
                confidence = "medio"
            else:
                confidence = "bajo"

            return DemandEstimate(
                confidence_level=confidence,
                estimated_monthly_volume=None,
                source_description="YouTube — reviews en video",
                notes=(
                    f"{len(listings)} videos encontrados con "
                    f"{total_views:,} visualizaciones totales. "
                    f"Canales: {', '.join(list(channels)[:5])}."
                ),
            )

        except Exception as exc:
            logger.warning("YouTube demand error: %s", exc)
            return DemandEstimate(
                confidence_level="bajo",
                source_description="YouTube — error",
                notes=f"No se pudo analizar videos: {exc}",
            )
