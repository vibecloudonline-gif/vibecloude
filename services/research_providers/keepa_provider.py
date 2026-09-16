from __future__ import annotations

from typing import Optional

from services.research_providers.base import DemandEstimate, ProductDataProvider, ProductListing, ProviderNotConfigured


class KeepaProvider(ProductDataProvider):
    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ProviderNotConfigured("KEEPA_API_KEY no configurada")
        self.api_key = api_key

    async def search_products(self, query: str, reference_url: Optional[str] = None) -> list[ProductListing]:
        raise NotImplementedError("Keepa provider pendiente de implementación con API real")

    async def estimate_demand(self, query: str) -> DemandEstimate:
        raise NotImplementedError("Keepa provider pendiente de implementación con API real")
