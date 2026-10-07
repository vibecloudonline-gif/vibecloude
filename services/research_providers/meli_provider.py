"""Mercado Libre API provider — precios reales de marketplaces LATAM."""
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

logger = logging.getLogger("research.meli")

MELI_SITES = {
    "AR": "MLA", "MX": "MLM", "BR": "MLB", "CO": "MCO",
    "CL": "MLC", "UY": "MLU", "PE": "MPE", "EC": "MEC",
}

MELI_CURRENCIES = {
    "ARS": "ARS", "MXN": "MXN", "BRL": "BRL", "COP": "COP",
    "CLP": "CLP", "UYU": "UYU", "PEN": "PEN", "USD": "USD",
}


class MeliProvider(ProductDataProvider):
    """Provider que usa la API pública de Mercado Libre (sin auth para búsqueda)."""

    def __init__(self, site_id: str = "MLA") -> None:
        self.site_id = site_id if site_id in MELI_SITES.values() else "MLA"
        self.base_url = f"https://api.mercadolibre.com/sites/{self.site_id}"

    async def search_products(
        self, query: str, reference_url: Optional[str] = None
    ) -> list[ProductListing]:
        params = {
            "q": query,
            "limit": 10,
            "sort": "relevance",
        }

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(f"{self.base_url}/search", params=params)
                resp.raise_for_status()
                data = resp.json()

            results = data.get("results", [])
            if not results:
                logger.info("MeLi search sin resultados para: %s", query)
                return []

            listings: list[ProductListing] = []
            for item in results[:8]:
                title = item.get("title", "")
                price_raw = item.get("price")
                currency = item.get("currency_id", "USD")
                item_id = item.get("id", "")
                permalink = item.get("permalink", "")
                sold_qty = item.get("sold_quantity", 0)

                if not title or price_raw is None:
                    continue

                try:
                    price = Decimal(str(price_raw)).quantize(Decimal("0.01"))
                except Exception:
                    continue

                # MeLi doesn't give ratings in search; we use sold_quantity as proxy
                review_count = sold_qty if sold_qty else None

                listings.append(ProductListing(
                    source=f"Mercado Libre ({self.site_id})",
                    title=title,
                    price=price,
                    currency=currency,
                    url=permalink or f"https://www.mercadolibre.com.ar/p/{item_id}",
                    rating=None,
                    review_count=review_count,
                    is_demo=False,
                ))

            return listings

        except httpx.HTTPStatusError as exc:
            logger.warning("MeLi search HTTP %d: %s", exc.response.status_code, exc)
            return []
        except Exception as exc:
            logger.warning("MeLi search error: %s", exc)
            return []

    async def estimate_demand(self, query: str) -> DemandEstimate:
        params = {"q": query, "limit": 10, "sort": "sold_quantity_desc"}

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(f"{self.base_url}/search", params=params)
                resp.raise_for_status()
                data = resp.json()

            results = data.get("results", [])
            total_available = data.get("paging", {}).get("total", 0)

            if not results:
                return DemandEstimate(
                    confidence_level="bajo",
                    estimated_monthly_volume=None,
                    source_description=f"Mercado Libre ({self.site_id}) — sin resultados",
                    notes=f"No se encontraron productos para '{query}'.",
                )

            total_sold = sum(r.get("sold_quantity", 0) for r in results)
            prices = [r.get("price", 0) for r in results if r.get("price")]
            avg_price = sum(prices) / len(prices) if prices else 0
            currency = results[0].get("currency_id", "USD") if results else "USD"

            # Estimate monthly: top 10 sold / lifespan assumption (~6 months avg)
            estimated_monthly = max(int(total_sold / 6), 50) if total_sold > 0 else None

            if total_available > 1000:
                confidence = "alto"
            elif total_available > 100:
                confidence = "medio"
            else:
                confidence = "bajo"

            return DemandEstimate(
                confidence_level=confidence,
                estimated_monthly_volume=estimated_monthly,
                source_description=f"Mercado Libre ({self.site_id}) — API pública",
                notes=(
                    f"{total_available} publicaciones encontradas. "
                    f"Top 10 vendieron {total_sold} unidades. "
                    f"Precio promedio: ${avg_price:,.2f} {currency}."
                ),
            )

        except Exception as exc:
            logger.warning("MeLi demand estimation error: %s", exc)
            return DemandEstimate(
                confidence_level="bajo",
                source_description=f"Mercado Libre ({self.site_id}) — error",
                notes=f"No se pudo estimar demanda: {exc}",
            )
