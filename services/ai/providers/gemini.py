"""Gemini provider adapter — wraps existing httpx calls to the Gemini REST API."""
from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

from services.ai.contracts import AIError, AIErrorCode, AIMessage, AIRequest, AIResponse, AIUsage
from services.ai.providers.base import AIProviderAdapter

logger = logging.getLogger("ai.providers.gemini")

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-3.5-flash"


class GeminiAdapter(AIProviderAdapter):
    provider_name = "gemini"

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.getenv("GEMINI_API_KEY", "")

    def validate_config(self) -> bool:
        return bool(self._api_key)

    def _get_api_key(self, request: AIRequest) -> str:
        key = request.metadata.get("api_key") or self._api_key
        if not key:
            raise AIError(
                AIErrorCode.authentication_error,
                self.provider_name,
                "GEMINI_API_KEY no configurada",
            )
        return key

    def _build_contents(self, messages: list[AIMessage]) -> list[dict[str, Any]]:
        contents: list[dict[str, Any]] = []
        for msg in messages:
            if msg.parts is not None:
                contents.append({"role": self._map_role(msg.role), "parts": msg.parts})
            else:
                contents.append({"role": self._map_role(msg.role), "parts": [{"text": msg.content}]})
        return contents

    @staticmethod
    def _map_role(role: str) -> str:
        return {"assistant": "model", "system": "user"}.get(role, role)

    async def generate(self, request: AIRequest) -> AIResponse:
        api_key = self._get_api_key(request)
        model = request.model or DEFAULT_MODEL
        url = f"{GEMINI_API_BASE}/{model}:generateContent?key={api_key}"

        payload: dict[str, Any] = {}

        if request.messages:
            payload["contents"] = self._build_contents(request.messages)

        if request.system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": request.system_prompt}]}

        if request.tools:
            payload["tools"] = request.tools

        gen_config: dict[str, Any] = {}
        if request.structured_output:
            gen_config["responseMimeType"] = "application/json"
        if gen_config:
            payload["generationConfig"] = gen_config

        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload, timeout=request.timeout)
        except httpx.TimeoutException as exc:
            raise AIError(AIErrorCode.timeout, self.provider_name, str(exc), retryable=True) from exc
        except httpx.RequestError as exc:
            raise AIError(AIErrorCode.network_error, self.provider_name, str(exc), retryable=True) from exc
        latency_ms = int((time.monotonic() - t0) * 1000)

        if resp.status_code == 429:
            raise AIError(AIErrorCode.rate_limit, self.provider_name, "Gemini rate limit", retryable=True, status_code=429)
        if resp.status_code != 200:
            raise AIError(
                AIErrorCode.provider_error, self.provider_name,
                f"Gemini API error {resp.status_code}: {resp.text[:300]}",
                retryable=resp.status_code >= 500, status_code=resp.status_code,
            )

        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise AIError(AIErrorCode.invalid_response, self.provider_name, "No candidates returned")

        content_obj = candidates[0].get("content", {})
        parts = content_obj.get("parts", [])
        if not parts:
            raise AIError(AIErrorCode.invalid_response, self.provider_name, "Empty response parts")

        first_part = parts[0]

        tool_calls: list[dict[str, Any]] = []
        text_content = ""

        if "functionCall" in first_part:
            fn = first_part["functionCall"]
            tool_calls.append({
                "name": fn["name"],
                "args": fn.get("args", {}),
                "raw_part": first_part,
            })
        else:
            text_content = first_part.get("text", "")

        usage_meta = data.get("usageMetadata", {})
        usage = AIUsage(
            input_tokens=usage_meta.get("promptTokenCount", 0),
            output_tokens=usage_meta.get("candidatesTokenCount", 0),
            total_tokens=usage_meta.get("totalTokenCount", 0),
        )

        finish_reason = candidates[0].get("finishReason", "")

        return AIResponse(
            request_id=request.request_id,
            provider=self.provider_name,
            model=model,
            content=text_content,
            tool_calls=tool_calls,
            usage=usage,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
        )
