"""Base interface for AI provider adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod

from services.ai.contracts import AIRequest, AIResponse


class AIProviderAdapter(ABC):
    provider_name: str = ""

    @abstractmethod
    async def generate(self, request: AIRequest) -> AIResponse:
        """Send a request and return a normalized response."""

    def validate_config(self) -> bool:
        """Return True if this provider is properly configured (has API key, etc)."""
        return False
