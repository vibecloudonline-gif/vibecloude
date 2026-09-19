from __future__ import annotations

import hashlib
import random
from decimal import Decimal
from typing import Optional

from services.research_providers.base import DemandEstimate, ProductDataProvider, ProductListing

_DEMO_TITLES = [
    "Kit Profesional Premium",
    "Pack Starter Económico",
    "Versión Deluxe Importada",
    "Alternativa Nacional Reforzada",
    "Edición Limitada Exclusiva",
    "Combo Familiar x3 Unidades",
    "Modelo Compacto Portátil",
    "Set Industrial Alta Demanda",
]

_DEMO_SOURCES = ["Amazon", "MercadoLibre", "demo"]


class MockProvider(ProductDataProvider):
    async def search_products(self, query: str, reference_url: Optional[str] = None) -> list[ProductListing]:
        seed = int(hashlib.sha256(query.encode()).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)

        count = rng.randint(3, 6)
        base_price = rng.uniform(15.0, 250.0)

        listings: list[ProductListing] = []
        for i in range(count):
            price = round(base_price * rng.uniform(0.6, 1.8), 2)
            listings.append(ProductListing(
                source=rng.choice(_DEMO_SOURCES),
                title=f"{rng.choice(_DEMO_TITLES)} - {query[:30]}",
                price=Decimal(str(price)),
                currency="USD",
                url=None,
                rating=Decimal(str(round(rng.uniform(2.5, 5.0), 2))),
                review_count=rng.randint(5, 2000),
                is_demo=True,
            ))
        return listings

    async def estimate_demand(self, query: str) -> DemandEstimate:
        seed = int(hashlib.sha256(query.encode()).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)

        return DemandEstimate(
            confidence_level="bajo",
            estimated_monthly_volume=rng.randint(50, 5000),
            source_description="Estimación referencial de mercado",
            notes="Estimación preliminar generada con datos de referencia.",
        )
