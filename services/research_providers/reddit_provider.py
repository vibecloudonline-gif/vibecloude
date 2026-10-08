"""Reddit provider — opiniones reales de consumidores."""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

import httpx

from services.research_providers.base import (
    DemandEstimate,
    ProductDataProvider,
    ProductListing,
)

logger = logging.getLogger("research.reddit")

SEARCH_URL = "https://www.reddit.com/search.json"

HEADERS = {
    "User-Agent": "VibeCloud/1.0 (market-research; contact: support@vibecloud.com)",
    "Accept": "application/json",
}

REVIEW_SUBREDDITS = [
    "BuyItForLife", "ProductReviews", "AmazonTopRated",
    "deals", "goodvalue", "shutupandtakemymoney",
]


class RedditProvider(ProductDataProvider):

    async def search_products(
        self, query: str, reference_url: Optional[str] = None
    ) -> list[ProductListing]:
        params = {
            "q": f"{query} review OR opinion OR recommend",
            "sort": "relevance",
            "t": "year",
            "limit": 15,
            "type": "link",
        }

        try:
            async with httpx.AsyncClient(timeout=15, headers=HEADERS, follow_redirects=True) as client:
                resp = await client.get(SEARCH_URL, params=params)
                resp.raise_for_status()
                data = resp.json()

            posts = data.get("data", {}).get("children", [])
            if not posts:
                logger.info("Reddit search sin resultados para: %s", query)
                return []

            listings: list[ProductListing] = []
            for post in posts[:10]:
                pd = post.get("data", {})
                title = pd.get("title", "")
                subreddit = pd.get("subreddit", "")
                score = pd.get("score", 0)
                num_comments = pd.get("num_comments", 0)
                permalink = pd.get("permalink", "")
                url = f"https://www.reddit.com{permalink}" if permalink else None

                if not title:
                    continue

                listings.append(ProductListing(
                    source=f"Reddit r/{subreddit}",
                    title=title[:200],
                    price=None,
                    currency="USD",
                    url=url,
                    rating=None,
                    review_count=score + num_comments,
                    is_demo=False,
                ))

            return listings

        except httpx.HTTPStatusError as exc:
            logger.warning("Reddit search HTTP %d: %s", exc.response.status_code, exc)
            return []
        except Exception as exc:
            logger.warning("Reddit search error: %s", exc)
            return []

    async def estimate_demand(self, query: str) -> DemandEstimate:
        params = {
            "q": query,
            "sort": "relevance",
            "t": "year",
            "limit": 25,
            "type": "link",
        }

        try:
            async with httpx.AsyncClient(timeout=15, headers=HEADERS, follow_redirects=True) as client:
                resp = await client.get(SEARCH_URL, params=params)
                resp.raise_for_status()
                data = resp.json()

            posts = data.get("data", {}).get("children", [])
            total_posts = data.get("data", {}).get("dist", 0) or len(posts)

            if not posts:
                return DemandEstimate(
                    confidence_level="bajo",
                    estimated_monthly_volume=None,
                    source_description="Reddit — sin resultados",
                    notes=f"No se encontraron discusiones sobre '{query}'.",
                )

            total_score = sum(p.get("data", {}).get("score", 0) for p in posts)
            total_comments = sum(p.get("data", {}).get("num_comments", 0) for p in posts)
            subreddits = set(p.get("data", {}).get("subreddit", "") for p in posts)

            if total_score > 5000 or total_comments > 1000:
                confidence = "alto"
            elif total_score > 500 or total_comments > 100:
                confidence = "medio"
            else:
                confidence = "bajo"

            return DemandEstimate(
                confidence_level=confidence,
                estimated_monthly_volume=None,
                source_description="Reddit — discusiones públicas",
                notes=(
                    f"{total_posts} posts encontrados en {len(subreddits)} subreddits. "
                    f"Engagement total: {total_score} upvotes, {total_comments} comentarios. "
                    f"Subreddits: {', '.join(list(subreddits)[:5])}."
                ),
            )

        except Exception as exc:
            logger.warning("Reddit demand error: %s", exc)
            return DemandEstimate(
                confidence_level="bajo",
                source_description="Reddit — error",
                notes=f"No se pudo analizar discusiones: {exc}",
            )
