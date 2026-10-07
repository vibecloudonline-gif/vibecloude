"""OpenAI provider adapter — uses the official openai SDK for GPT-4o and family."""
from __future__ import annotations

import logging
import os
import time
from typing import Any

from services.ai.contracts import AIError, AIErrorCode, AIRequest, AIResponse, AIUsage
from services.ai.providers.base import AIProviderAdapter

logger = logging.getLogger("ai.providers.openai")

DEFAULT_MODEL = "gpt-4o"


class OpenAIAdapter(AIProviderAdapter):
    provider_name = "openai"

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")

    def validate_config(self) -> bool:
        return bool(self._api_key)

    async def generate(self, request: AIRequest) -> AIResponse:
        if not self._api_key:
            raise AIError(
                AIErrorCode.authentication_error,
                self.provider_name,
                "OPENAI_API_KEY no configurada",
            )

        try:
            from openai import AsyncOpenAI, APIError, APITimeoutError, RateLimitError, AuthenticationError
        except ImportError:
            raise AIError(
                AIErrorCode.provider_error,
                self.provider_name,
                "SDK openai no instalado. Ejecutá: pip install openai",
            )

        client = AsyncOpenAI(api_key=self._api_key)
        model = request.model or DEFAULT_MODEL

        messages: list[dict[str, str]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        for msg in request.messages:
            role = "assistant" if msg.role in ("model", "assistant") else msg.role
            if role == "system" and messages and messages[0]["role"] == "system":
                messages[0]["content"] += "\n" + msg.content
                continue
            messages.append({"role": role, "content": msg.content})

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "timeout": request.timeout,
        }

        if request.tools:
            kwargs["tools"] = self._convert_tools(request.tools)
            if request.tool_choice:
                kwargs["tool_choice"] = request.tool_choice

        t0 = time.monotonic()
        try:
            response = await client.chat.completions.create(**kwargs)
        except APITimeoutError as exc:
            raise AIError(AIErrorCode.timeout, self.provider_name, str(exc), retryable=True) from exc
        except RateLimitError as exc:
            raise AIError(AIErrorCode.rate_limit, self.provider_name, str(exc), retryable=True, status_code=429) from exc
        except AuthenticationError as exc:
            raise AIError(AIErrorCode.authentication_error, self.provider_name, str(exc)) from exc
        except APIError as exc:
            raise AIError(
                AIErrorCode.provider_error, self.provider_name,
                f"OpenAI API error: {exc}",
                retryable=getattr(exc, "status_code", 500) >= 500,
                status_code=getattr(exc, "status_code", None),
            ) from exc
        finally:
            await client.close()

        latency_ms = int((time.monotonic() - t0) * 1000)

        choice = response.choices[0] if response.choices else None
        if not choice:
            raise AIError(AIErrorCode.invalid_response, self.provider_name, "No choices returned")

        text_content = choice.message.content or ""
        finish_reason = choice.finish_reason or ""

        tool_calls: list[dict[str, Any]] = []
        if choice.message.tool_calls:
            import json
            for tc in choice.message.tool_calls:
                tool_calls.append({
                    "name": tc.function.name,
                    "args": json.loads(tc.function.arguments) if tc.function.arguments else {},
                    "id": tc.id,
                })

        usage = AIUsage()
        if response.usage:
            usage = AIUsage(
                input_tokens=response.usage.prompt_tokens or 0,
                output_tokens=response.usage.completion_tokens or 0,
                total_tokens=response.usage.total_tokens or 0,
            )

        result = AIResponse(
            request_id=request.request_id,
            provider=self.provider_name,
            model=model,
            content=text_content,
            tool_calls=tool_calls,
            usage=usage,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
        )
        self.log_call(request, result)
        return result

    @staticmethod
    def _convert_tools(gemini_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert Gemini-format function declarations to OpenAI tools format."""
        openai_tools: list[dict[str, Any]] = []
        for tool_group in gemini_tools:
            declarations = tool_group.get("function_declarations") or tool_group.get("functionDeclarations", [])
            for fn in declarations:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": fn["name"],
                        "description": fn.get("description", ""),
                        "parameters": fn.get("parameters", {"type": "object", "properties": {}}),
                    },
                })
        if not openai_tools and gemini_tools:
            for item in gemini_tools:
                if "type" in item and item["type"] == "function":
                    openai_tools.append(item)
        return openai_tools
