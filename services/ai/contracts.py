"""Normalized contracts for the AI Gateway.

Every AI call — regardless of provider — uses AIRequest in, AIResponse out.
Provider and model are OPTIONAL: when omitted, the future Cognitive Router
will decide. For now, callers specify them explicitly.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class AIMessage(BaseModel):
    role: str  # "user", "model", "assistant", "tool", "system"
    content: str = ""
    parts: Optional[list[dict[str, Any]]] = None


class AIRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: uuid4().hex)
    tenant_id: Optional[int] = None
    task: str = "chat"
    messages: list[AIMessage] = Field(default_factory=list)
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 2048
    tools: Optional[list[dict[str, Any]]] = None
    tool_choice: Optional[str] = None
    structured_output: bool = False
    output_schema: Optional[dict[str, Any]] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    timeout: float = 30.0


class AIUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class AIResponse(BaseModel):
    request_id: str
    provider: str
    model: str
    content: str = ""
    structured_data: Optional[dict[str, Any]] = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    usage: AIUsage = Field(default_factory=AIUsage)
    latency_ms: int = 0
    finish_reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AIErrorCode(str, Enum):
    provider_error = "provider_error"
    authentication_error = "authentication_error"
    rate_limit = "rate_limit"
    timeout = "timeout"
    network_error = "network_error"
    invalid_request = "invalid_request"
    invalid_response = "invalid_response"
    schema_error = "schema_error"
    tool_error = "tool_error"
    unknown_error = "unknown_error"


class AIError(Exception):
    def __init__(
        self,
        code: AIErrorCode,
        provider: str,
        message: str = "",
        retryable: bool = False,
        status_code: Optional[int] = None,
    ):
        self.code = code
        self.provider = provider
        self.retryable = retryable
        self.status_code = status_code
        super().__init__(message)
