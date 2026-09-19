"""Claude provider adapter — wraps the existing AnthropicClient (SDK-based)."""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

from services.ai.contracts import AIError, AIErrorCode, AIRequest, AIResponse, AIUsage
from services.ai.providers.base import AIProviderAdapter

logger = logging.getLogger("ai.providers.claude")

DEFAULT_MODEL = "claude-opus-5"


class ClaudeAdapter(AIProviderAdapter):
    provider_name = "claude"

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self._credit_exhausted_until = 0.0

    def validate_config(self) -> bool:
        if time.monotonic() < self._credit_exhausted_until:
            return False
        return bool(self._api_key)

    async def generate(self, request: AIRequest) -> AIResponse:
        if not self._api_key or time.monotonic() < self._credit_exhausted_until:
            raise AIError(
                AIErrorCode.authentication_error,
                self.provider_name,
                "ANTHROPIC_API_KEY no configurada o sin crédito disponible",
            )

        try:
            import anthropic
        except ImportError as exc:
            raise AIError(
                AIErrorCode.provider_error,
                self.provider_name,
                "anthropic package not installed",
            ) from exc

        model = request.model or DEFAULT_MODEL
        client = anthropic.AsyncAnthropic(api_key=self._api_key)

        content_blocks: list[dict[str, Any]] = []

        image_path: Optional[str] = request.metadata.get("reference_image_path")
        if image_path:
            content_blocks.append(self._build_image_block(image_path))

        user_text = ""
        if request.messages:
            user_text = request.messages[-1].content
        content_blocks.append({"type": "text", "text": user_text})

        t0 = time.monotonic()
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=request.max_tokens,
                system=request.system_prompt or "",
                messages=[{"role": "user", "content": content_blocks}],
            )
        except anthropic.APIError as exc:
            code = AIErrorCode.provider_error
            retryable = False
            msg = str(exc).lower()
            if hasattr(exc, "status_code"):
                if exc.status_code == 429:
                    code = AIErrorCode.rate_limit
                    retryable = True
                elif exc.status_code in (400, 402) and any(term in msg for term in ["credit", "balance", "quota", "billing"]):
                    code = AIErrorCode.authentication_error
                    retryable = False
                    self._credit_exhausted_until = time.monotonic() + 300.0
                    logger.warning("Claude reportó saldo o crédito insuficiente en cuenta Anthropic. Pausando Claude 5m para fallback inmediato.")
                elif exc.status_code >= 500:
                    retryable = True
            raise AIError(code, self.provider_name, str(exc), retryable=retryable) from exc
        except Exception as exc:
            raise AIError(AIErrorCode.network_error, self.provider_name, str(exc), retryable=True) from exc
        latency_ms = int((time.monotonic() - t0) * 1000)

        if response.stop_reason == "refusal":
            raise AIError(AIErrorCode.provider_error, self.provider_name, "Claude rechazó la solicitud (refusal)")

        text_parts = [block.text for block in response.content if block.type == "text"]
        text_content = "".join(text_parts)

        usage = AIUsage(
            input_tokens=getattr(response.usage, "input_tokens", 0),
            output_tokens=getattr(response.usage, "output_tokens", 0),
            total_tokens=getattr(response.usage, "input_tokens", 0) + getattr(response.usage, "output_tokens", 0),
        )

        return AIResponse(
            request_id=request.request_id,
            provider=self.provider_name,
            model=model,
            content=text_content,
            usage=usage,
            latency_ms=latency_ms,
            finish_reason=response.stop_reason or "",
        )

    @staticmethod
    def _build_image_block(path: str) -> dict[str, Any]:
        import base64
        import mimetypes

        mime_type, _ = mimetypes.guess_type(path)
        if not mime_type or not mime_type.startswith("image/"):
            mime_type = "image/jpeg"
        with open(path, "rb") as f:
            encoded = base64.standard_b64encode(f.read()).decode("ascii")
        return {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": encoded}}
