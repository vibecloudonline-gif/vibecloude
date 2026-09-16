from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass
class ProductListing:
    source: str
    title: str
    price: Optional[Decimal]
    currency: str = "USD"
    url: Optional[str] = None
    rating: Optional[Decimal] = None
    review_count: Optional[int] = None
    is_demo: bool = False


@dataclass
class DemandEstimate:
    confidence_level: str  # alto, medio, bajo, no_disponible
    estimated_monthly_volume: Optional[int] = None
    source_description: Optional[str] = None
    notes: Optional[str] = None


class ProviderNotConfigured(Exception):
    pass


class ProductDataProvider(ABC):
    @abstractmethod
    async def search_products(self, query: str, reference_url: Optional[str] = None) -> list[ProductListing]:
        ...

    @abstractmethod
    async def estimate_demand(self, query: str) -> DemandEstimate:
        ...
