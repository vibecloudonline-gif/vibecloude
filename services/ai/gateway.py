"""AI Gateway — single entry point for all AI provider calls.

No routing logic (Cognitive Router is FASE 2+). This layer:
- Resolves which adapter to use from the explicit provider/model in the request
- Enforces timeout
- Normalizes errors into AIError
- Logs every call (request_id, tenant_id, provider, model, task, status, latency)
"""
from __future__ import annotations

import logging
from typing import Optional

from services.ai.contracts import AIError, AIErrorCode, AIRequest, AIResponse
from services.ai.providers.base import AIProviderAdapter
from services.ai.providers.gemini import GeminiAdapter
from services.ai.providers.claude import ClaudeAdapter
from services.ai.providers.qwen import QwenAdapter

logger = logging.getLogger("ai.gateway")


class AIGateway:
    def __init__(self):
        self._adapters: dict[str, AIProviderAdapter] = {}
        self._register_defaults()

    def _register_defaults(self):
        self.register("gemini", GeminiAdapter())
        self.register("claude", ClaudeAdapter())
        self.register("qwen", QwenAdapter())

    def register(self, name: str, adapter: AIProviderAdapter):
        self._adapters[name] = adapter

    def get_adapter(self, provider: str) -> AIProviderAdapter:
        adapter = self._adapters.get(provider)
        if not adapter:
            raise AIError(
                AIErrorCode.invalid_request,
                provider,
                f"Provider '{provider}' not registered",
            )
        return adapter

    def list_providers(self) -> dict[str, bool]:
        return {name: adapter.validate_config() for name, adapter in self._adapters.items()}

    async def generate(self, request: AIRequest) -> AIResponse:
        provider_name = request.provider
        if not provider_name:
            provider_name = self._infer_provider(request.model)

        adapter = self.get_adapter(provider_name)

        logger.info(
            "ai.gateway.request | req=%s tenant=%s task=%s provider=%s model=%s",
            request.request_id[:12], request.tenant_id,
            request.task, provider_name, request.model or "(default)",
        )

        try:
            response = await adapter.generate(request)
        except AIError:
            raise
        except Exception as exc:
            logger.error(
                "ai.gateway.error | req=%s provider=%s error=%s",
                request.request_id[:12], provider_name, exc,
            )
            raise AIError(
                AIErrorCode.unknown_error,
                provider_name,
                str(exc),
            ) from exc

        logger.info(
            "ai.gateway.response | req=%s provider=%s model=%s latency=%dms tokens=%d status=%s",
            response.request_id[:12], response.provider, response.model,
            response.latency_ms, response.usage.total_tokens, response.finish_reason,
        )

        return response

    @staticmethod
    def _infer_provider(model: Optional[str]) -> str:
        if not model:
            return "gemini"
        m = model.lower()
        if "claude" in m:
            return "claude"
        if "qwen" in m:
            return "qwen"
        if "gemini" in m:
            return "gemini"
        return "gemini"


ai_gateway = AIGateway()
