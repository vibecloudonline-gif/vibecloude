"""Base interface for AI provider adapters."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from services.ai.contracts import AIRequest, AIResponse

_ai_logger = logging.getLogger("ai.calls")


class AIProviderAdapter(ABC):
    provider_name: str = ""

    @abstractmethod
    async def generate(self, request: AIRequest) -> AIResponse:
        """Send a request and return a normalized response."""

    def validate_config(self) -> bool:
        """Return True if this provider is properly configured (has API key, etc)."""
        return False

    def log_call(
        self,
        request: AIRequest,
        response: AIResponse | None = None,
        *,
        is_fallback: bool = False,
        fallback_reason: str = "",
        error: str = "",
    ) -> None:
        _ai_logger.info(
            "ai_call provider=%s model=%s tenant_id=%s task=%s "
            "latency_ms=%d tokens_in=%d tokens_out=%d "
            "is_fallback=%s fallback_reason=%s error=%s",
            self.provider_name,
            response.model if response else (request.model or "?"),
            request.tenant_id or "?",
            request.task,
            response.latency_ms if response else 0,
            response.usage.input_tokens if response else 0,
            response.usage.output_tokens if response else 0,
            is_fallback,
            fallback_reason or "",
            error or "",
        )
