"""Qwen (DashScope) provider adapter — wraps the existing QwenClient pattern."""
from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

from services.ai.contracts import AIError, AIErrorCode, AIRequest, AIResponse, AIUsage
from services.ai.providers.base import AIProviderAdapter

logger = logging.getLogger("ai.providers.qwen")

QWEN_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
DEFAULT_MODEL = "qwen-plus"


class QwenAdapter(AIProviderAdapter):
    provider_name = "qwen"

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.getenv("QWEN_API_KEY", "")
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
                "QWEN_API_KEY no configurada o sin crédito disponible",
            )

        model = request.model or DEFAULT_MODEL

        oai_messages: list[dict[str, str]] = []
        if request.system_prompt:
            oai_messages.append({"role": "system", "content": request.system_prompt})
        for msg in request.messages:
            role = "assistant" if msg.role in ("model", "assistant") else msg.role
            oai_messages.append({"role": role, "content": msg.content})

        payload = {"model": model, "messages": oai_messages}
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens

        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(QWEN_API_URL, json=payload, headers=headers, timeout=request.timeout)
        except httpx.TimeoutException as exc:
            raise AIError(AIErrorCode.timeout, self.provider_name, str(exc), retryable=True) from exc
        except httpx.RequestError as exc:
            raise AIError(AIErrorCode.network_error, self.provider_name, str(exc), retryable=True) from exc
        latency_ms = int((time.monotonic() - t0) * 1000)

        if resp.status_code == 429:
            raise AIError(AIErrorCode.rate_limit, self.provider_name, "Qwen rate limit", retryable=True, status_code=429)
        if resp.status_code != 200:
            resp_text = resp.text.lower()
            code = AIErrorCode.provider_error
            retryable = resp.status_code >= 500
            if resp.status_code in (400, 402, 403) and any(
                term in resp_text for term in ["credit", "balance", "quota", "arrears", "insufficient"]
            ):
                code = AIErrorCode.authentication_error
                retryable = False
                self._credit_exhausted_until = time.monotonic() + 300.0
                logger.warning("Qwen reportó saldo o crédito insuficiente en cuenta Alibaba. Pausando Qwen 5m para fallback inmediato.")

            raise AIError(
                code, self.provider_name,
                f"Qwen API error {resp.status_code}: {resp.text[:300]}",
                retryable=retryable, status_code=resp.status_code,
            )

        data = resp.json()
        try:
            text_content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise AIError(AIErrorCode.invalid_response, self.provider_name, f"Unexpected Qwen response: {data}") from exc

        oai_usage = data.get("usage", {})
        usage = AIUsage(
            input_tokens=oai_usage.get("prompt_tokens", 0),
            output_tokens=oai_usage.get("completion_tokens", 0),
            total_tokens=oai_usage.get("total_tokens", 0),
        )

        finish = data.get("choices", [{}])[0].get("finish_reason", "")

        return AIResponse(
            request_id=request.request_id,
            provider=self.provider_name,
            model=model,
            content=text_content,
            usage=usage,
            latency_ms=latency_ms,
            finish_reason=finish,
        )
