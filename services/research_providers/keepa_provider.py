"""Keepa API provider — precios reales de Amazon con historial."""
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

logger = logging.getLogger("research.keepa")

KEEPA_BASE = "https://api.keepa.com"

# Keepa domain IDs
KEEPA_DOMAINS = {
    "us": 1, "uk": 2, "de": 3, "fr": 4, "jp": 5,
    "ca": 6, "it": 8, "es": 9, "mx": 11, "br": 13,
}


def _cents_to_dollars(cents: int | None) -> Decimal | None:
    if cents is None or cents < 0:
        return None
    return Decimal(str(cents / 100)).quantize(Decimal("0.01"))


class KeepaProvider(ProductDataProvider):
    def __init__(self, api_key: str, domain: str = "us") -> None:
        if not api_key:
            raise ProviderNotConfigured("KEEPA_API_KEY no configurada")
        self.api_key = api_key
        self.domain_id = KEEPA_DOMAINS.get(domain, 1)

    async def search_products(
        self, query: str, reference_url: Optional[str] = None
    ) -> list[ProductListing]:
        params = {
            "key": self.api_key,
            "domain": self.domain_id,
            "type": "product",
            "term": query,
            "page": 0,
            "perPage": 10,
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(f"{KEEPA_BASE}/search", params=params)
                resp.raise_for_status()
                data = resp.json()

            asin_list = data.get("asinList", [])
            if not asin_list:
                logger.info("Keepa search sin resultados para: %s", query)
                return []

            asins = asin_list[:8]
            return await self._fetch_products(asins)

        except httpx.HTTPStatusError as exc:
            logger.warning("Keepa search HTTP %d: %s", exc.response.status_code, exc)
            return []
        except Exception as exc:
            logger.warning("Keepa search error: %s", exc)
            return []

    async def _fetch_products(self, asins: list[str]) -> list[ProductListing]:
        params = {
            "key": self.api_key,
            "domain": self.domain_id,
            "asin": ",".join(asins),
            "stats": 90,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{KEEPA_BASE}/product", params=params)
            resp.raise_for_status()
            data = resp.json()

        listings: list[ProductListing] = []
        for product in data.get("products", []):
            title = product.get("title", "")
            asin = product.get("asin", "")
            stats = product.get("stats", {})

            current_prices = stats.get("current", [])
            avg_prices = stats.get("avg90", [])

            # Index 0 = Amazon price, index 1 = new 3rd party
            price = None
            if current_prices and len(current_prices) > 0:
                price = _cents_to_dollars(current_prices[0])
            if price is None and current_prices and len(current_prices) > 1:
                price = _cents_to_dollars(current_prices[1])
            if price is None and avg_prices and len(avg_prices) > 0:
                price = _cents_to_dollars(avg_prices[0])

            rating_val = None
            review_count = None
            if stats.get("rating"):
                try:
                    rating_val = Decimal(str(stats["rating"] / 10)).quantize(Decimal("0.1"))
                except Exception:
                    pass
            if stats.get("reviewCount"):
                review_count = int(stats["reviewCount"])

            if title and price is not None:
                listings.append(ProductListing(
                    source="Amazon (Keepa)",
                    title=title,
                    price=price,
                    currency="USD",
                    url=f"https://www.amazon.com/dp/{asin}",
                    rating=rating_val,
                    review_count=review_count,
                    is_demo=False,
                ))

        return listings

    async def estimate_demand(self, query: str) -> DemandEstimate:
        params = {
            "key": self.api_key,
            "domain": self.domain_id,
            "type": "product",
            "term": query,
            "page": 0,
            "perPage": 5,
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(f"{KEEPA_BASE}/search", params=params)
                resp.raise_for_status()
                data = resp.json()

            asin_list = data.get("asinList", [])
            if not asin_list:
                return DemandEstimate(
                    confidence_level="bajo",
                    estimated_monthly_volume=None,
                    source_description="Keepa API — sin resultados",
                    notes=f"No se encontraron productos en Amazon para '{query}'.",
                )

            products = await self._fetch_products(asin_list[:5])
            total_reviews = sum(p.review_count or 0 for p in products)

            # Heuristic: ~1% of buyers leave reviews, monthly estimate
            estimated_volume = max(total_reviews * 3, 100) if total_reviews > 0 else None

            if total_reviews > 5000:
                confidence = "alto"
            elif total_reviews > 500:
                confidence = "medio"
            else:
                confidence = "bajo"

            avg_price = None
            prices = [p.price for p in products if p.price]
            if prices:
                avg_price = sum(prices, Decimal("0")) / len(prices)

            return DemandEstimate(
                confidence_level=confidence,
                estimated_monthly_volume=estimated_volume,
                source_description="Keepa API — historial de Amazon",
                notes=(
                    f"Basado en {len(products)} productos encontrados con "
                    f"{total_reviews} reviews totales. "
                    f"Precio promedio: ${avg_price:.2f} USD."
                    if avg_price else
                    f"Basado en {len(products)} productos encontrados."
                ),
            )

        except Exception as exc:
            logger.warning("Keepa demand estimation error: %s", exc)
            return DemandEstimate(
                confidence_level="bajo",
                source_description="Keepa API — error",
                notes=f"No se pudo estimar demanda: {exc}",
            )
