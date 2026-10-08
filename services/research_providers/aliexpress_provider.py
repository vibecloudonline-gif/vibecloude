"""AliExpress provider — precios de proveedores para calcular margen."""
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

logger = logging.getLogger("research.aliexpress")

SEARCH_URL = "https://www.aliexpress.com/fn/search-pc/index"
FALLBACK_URL = "https://www.aliexpress.com/glosearch/api/product"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
    "Referer": "https://www.aliexpress.com/",
}


def _parse_price(raw: str | float | int | None) -> Optional[Decimal]:
    if raw is None:
        return None
    try:
        cleaned = str(raw).replace(",", "").replace("US $", "").replace("$", "").strip()
        if "-" in cleaned:
            cleaned = cleaned.split("-")[0].strip()
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except Exception:
        return None


class AliExpressProvider(ProductDataProvider):

    async def search_products(
        self, query: str, reference_url: Optional[str] = None
    ) -> list[ProductListing]:
        params = {
            "SearchText": query,
            "page": 1,
            "limit": 10,
            "sort_type": "default",
        }

        try:
            async with httpx.AsyncClient(timeout=20, headers=HEADERS, follow_redirects=True) as client:
                resp = await client.get(SEARCH_URL, params=params)

                if resp.status_code != 200:
                    resp = await client.get(
                        FALLBACK_URL,
                        params={"CatId": "0", "SearchText": query, "page": "1", "limit": "10"},
                    )

                if resp.status_code != 200:
                    logger.warning("AliExpress search HTTP %d", resp.status_code)
                    return []

                data = resp.json()

            items = (
                data.get("data", {}).get("root", {}).get("fields", {}).get("mods", {}).get("itemList", {}).get("content", [])
                or data.get("items", [])
                or data.get("data", {}).get("items", [])
                or []
            )

            if not items and isinstance(data.get("data"), dict):
                for key in ("productList", "products", "result"):
                    items = data["data"].get(key, [])
                    if items:
                        break

            listings: list[ProductListing] = []
            for item in items[:10]:
                title = (
                    item.get("title", {}).get("displayTitle", "")
                    if isinstance(item.get("title"), dict)
                    else item.get("title", "")
                )
                if not title:
                    title = item.get("name", "") or item.get("productTitle", "")

                price_raw = (
                    item.get("prices", {}).get("salePrice", {}).get("minPrice")
                    if isinstance(item.get("prices"), dict)
                    else item.get("price", None) or item.get("salePrice", None)
                )
                if price_raw is None and isinstance(item.get("price"), dict):
                    price_raw = item["price"].get("min", item["price"].get("value"))

                price = _parse_price(price_raw)

                product_id = item.get("productId", "") or item.get("itemId", "") or item.get("id", "")
                url = item.get("productDetailUrl", "") or item.get("itemUrl", "")
                if not url and product_id:
                    url = f"https://www.aliexpress.com/item/{product_id}.html"

                orders_raw = item.get("trade", {}).get("tradeDesc", "") if isinstance(item.get("trade"), dict) else ""
                if not orders_raw:
                    orders_raw = str(item.get("orders", "") or item.get("totalOrders", "") or "")

                order_count = None
                if orders_raw:
                    import re
                    nums = re.findall(r"[\d,]+", str(orders_raw).replace(",", ""))
                    if nums:
                        try:
                            order_count = int(nums[0])
                        except ValueError:
                            pass

                rating_raw = item.get("evaluation", "") or item.get("starRating", "") or item.get("averageStar", "")
                rating = None
                if rating_raw:
                    try:
                        rating = Decimal(str(rating_raw)).quantize(Decimal("0.1"))
                    except Exception:
                        pass

                if title and price is not None:
                    listings.append(ProductListing(
                        source="AliExpress",
                        title=title[:200],
                        price=price,
                        currency="USD",
                        url=url,
                        rating=rating,
                        review_count=order_count,
                        is_demo=False,
                    ))

            return listings

        except Exception as exc:
            logger.warning("AliExpress search error: %s", exc)
            return []

    async def estimate_demand(self, query: str) -> DemandEstimate:
        try:
            listings = await self.search_products(query)
            if not listings:
                return DemandEstimate(
                    confidence_level="bajo",
                    estimated_monthly_volume=None,
                    source_description="AliExpress — sin resultados",
                    notes=f"No se encontraron productos para '{query}'.",
                )

            total_orders = sum(p.review_count or 0 for p in listings)
            prices = [p.price for p in listings if p.price]
            avg_price = sum(prices, Decimal("0")) / len(prices) if prices else None

            estimated_monthly = max(int(total_orders / 3), 100) if total_orders > 0 else None

            if total_orders > 10000:
                confidence = "alto"
            elif total_orders > 1000:
                confidence = "medio"
            else:
                confidence = "bajo"

            return DemandEstimate(
                confidence_level=confidence,
                estimated_monthly_volume=estimated_monthly,
                source_description="AliExpress — pedidos globales",
                notes=(
                    f"{len(listings)} productos encontrados con "
                    f"{total_orders} pedidos totales. "
                    f"Precio proveedor promedio: US${avg_price:.2f}."
                    if avg_price else
                    f"{len(listings)} productos encontrados."
                ),
            )

        except Exception as exc:
            logger.warning("AliExpress demand error: %s", exc)
            return DemandEstimate(
                confidence_level="bajo",
                source_description="AliExpress — error",
                notes=f"No se pudo estimar demanda: {exc}",
            )
