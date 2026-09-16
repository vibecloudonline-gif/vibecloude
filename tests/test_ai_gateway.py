"""Tests for the AI Gateway (FASE 1).

Tests contracts, adapters, gateway routing, timeout, errors, tenant_id,
tool calls, and integration (Alex→Gateway→Mock, Landing→Gateway→Mock).
All tests use mocks — no real API calls.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.ai.contracts import AIError, AIErrorCode, AIMessage, AIRequest, AIResponse, AIUsage
from services.ai.providers.base import AIProviderAdapter
from services.ai.providers.gemini import GeminiAdapter
from services.ai.providers.claude import ClaudeAdapter
from services.ai.providers.qwen import QwenAdapter
from services.ai.gateway import AIGateway


@pytest.fixture
def anyio_backend():
    return 'asyncio'


# =====================================================================
# 1. AIRequest validation
# =====================================================================

def test_valid_request():
    req = AIRequest(
        tenant_id=1,
        task="chat",
        messages=[AIMessage(role="user", content="hello")],
        provider="gemini",
    )
    assert req.request_id
    assert req.tenant_id == 1
    assert req.provider == "gemini"
    assert req.timeout == 30.0

def test_request_defaults():
    req = AIRequest()
    assert req.task == "chat"
    assert req.provider is None
    assert req.model is None
    assert req.temperature == 0.7
    assert req.max_tokens == 2048

def test_request_id_unique():
    r1 = AIRequest()
    r2 = AIRequest()
    assert r1.request_id != r2.request_id


# =====================================================================
# 2. AIResponse normalization
# =====================================================================

def test_response_fields():
    resp = AIResponse(
        request_id="abc123",
        provider="gemini",
        model="gemini-3.5-flash",
        content="Hello world",
        usage=AIUsage(input_tokens=10, output_tokens=5, total_tokens=15),
        latency_ms=200,
        finish_reason="STOP",
    )
    assert resp.content == "Hello world"
    assert resp.usage.total_tokens == 15
    assert resp.tool_calls == []

def test_response_with_tool_calls():
    resp = AIResponse(
        request_id="abc",
        provider="gemini",
        model="test",
        tool_calls=[{"name": "get_stock", "args": {"id": 1}}],
    )
    assert len(resp.tool_calls) == 1


# =====================================================================
# 3. AIError classification
# =====================================================================

def test_error_code():
    err = AIError(AIErrorCode.rate_limit, "gemini", "429", retryable=True, status_code=429)
    assert err.code == AIErrorCode.rate_limit
    assert err.provider == "gemini"
    assert err.retryable is True
    assert err.status_code == 429

def test_error_is_exception():
    with pytest.raises(AIError):
        raise AIError(AIErrorCode.timeout, "claude", "timed out")


# =====================================================================
# 4. Provider adapter - validate_config
# =====================================================================

def test_gemini_no_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    adapter = GeminiAdapter(api_key="")
    assert adapter.validate_config() is False

def test_gemini_with_key():
    adapter = GeminiAdapter(api_key="fake-key")
    assert adapter.validate_config() is True

def test_claude_no_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    adapter = ClaudeAdapter(api_key="")
    assert adapter.validate_config() is False

def test_claude_with_key():
    adapter = ClaudeAdapter(api_key="fake-key")
    assert adapter.validate_config() is True

def test_qwen_no_key(monkeypatch):
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    adapter = QwenAdapter(api_key="")
    assert adapter.validate_config() is False

def test_qwen_with_key():
    adapter = QwenAdapter(api_key="fake-key")
    assert adapter.validate_config() is True


# =====================================================================
# Helper for mocking httpx
# =====================================================================

def _mock_httpx(mock_response):
    """Returns a context-managed patch for httpx.AsyncClient."""
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_cm, mock_client


# =====================================================================
# 5. Gemini adapter - mocked HTTP
# =====================================================================

async def test_gemini_generate_text():
    adapter = GeminiAdapter(api_key="fake")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": "Hello"}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 3, "totalTokenCount": 8},
    }
    mock_cm, _ = _mock_httpx(mock_response)

    with patch("services.ai.providers.gemini.httpx.AsyncClient", return_value=mock_cm):
        req = AIRequest(
            messages=[AIMessage(role="user", content="hi")],
            provider="gemini",
            model="gemini-3.5-flash",
            metadata={"api_key": "fake"},
        )
        resp = await adapter.generate(req)

    assert resp.provider == "gemini"
    assert resp.content == "Hello"
    assert resp.usage.total_tokens == 8


async def test_gemini_generate_tool_call():
    adapter = GeminiAdapter(api_key="fake")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "candidates": [{"content": {"parts": [{"functionCall": {"name": "get_stock", "args": {"id": 1}}}]}}],
    }
    mock_cm, _ = _mock_httpx(mock_response)

    with patch("services.ai.providers.gemini.httpx.AsyncClient", return_value=mock_cm):
        req = AIRequest(
            messages=[AIMessage(role="user", content="stock?")],
            provider="gemini",
            metadata={"api_key": "fake"},
        )
        resp = await adapter.generate(req)

    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0]["name"] == "get_stock"
    assert resp.content == ""


async def test_gemini_rate_limit():
    adapter = GeminiAdapter(api_key="fake")
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.text = "rate limited"
    mock_cm, _ = _mock_httpx(mock_response)

    with patch("services.ai.providers.gemini.httpx.AsyncClient", return_value=mock_cm):
        req = AIRequest(messages=[AIMessage(role="user", content="hi")], metadata={"api_key": "fake"})
        with pytest.raises(AIError) as exc_info:
            await adapter.generate(req)
        assert exc_info.value.code == AIErrorCode.rate_limit
        assert exc_info.value.retryable is True


async def test_gemini_timeout():
    import httpx as real_httpx
    adapter = GeminiAdapter(api_key="fake")

    mock_client = AsyncMock()
    mock_client.post.side_effect = real_httpx.TimeoutException("timed out")
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("services.ai.providers.gemini.httpx.AsyncClient", return_value=mock_cm):
        req = AIRequest(messages=[AIMessage(role="user", content="hi")], timeout=1.0, metadata={"api_key": "fake"})
        with pytest.raises(AIError) as exc_info:
            await adapter.generate(req)
        assert exc_info.value.code == AIErrorCode.timeout


async def test_gemini_auth_error_no_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    adapter = GeminiAdapter(api_key="")
    req = AIRequest(messages=[AIMessage(role="user", content="hi")])
    with pytest.raises(AIError) as exc_info:
        await adapter.generate(req)
    assert exc_info.value.code == AIErrorCode.authentication_error


async def test_gemini_invalid_response_no_candidates():
    adapter = GeminiAdapter(api_key="fake")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"candidates": []}
    mock_cm, _ = _mock_httpx(mock_response)

    with patch("services.ai.providers.gemini.httpx.AsyncClient", return_value=mock_cm):
        req = AIRequest(messages=[AIMessage(role="user", content="hi")], metadata={"api_key": "fake"})
        with pytest.raises(AIError) as exc_info:
            await adapter.generate(req)
        assert exc_info.value.code == AIErrorCode.invalid_response


# =====================================================================
# 6. Qwen adapter - mocked HTTP
# =====================================================================

async def test_qwen_generate_text():
    adapter = QwenAdapter(api_key="fake")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Hola"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
    }
    mock_cm, _ = _mock_httpx(mock_response)

    with patch("services.ai.providers.qwen.httpx.AsyncClient", return_value=mock_cm):
        req = AIRequest(
            messages=[AIMessage(role="user", content="hola")],
            system_prompt="test",
            provider="qwen",
        )
        resp = await adapter.generate(req)

    assert resp.provider == "qwen"
    assert resp.content == "Hola"
    assert resp.usage.total_tokens == 13


async def test_qwen_auth_error(monkeypatch):
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    adapter = QwenAdapter(api_key="")
    req = AIRequest(messages=[AIMessage(role="user", content="hi")])
    with pytest.raises(AIError) as exc_info:
        await adapter.generate(req)
    assert exc_info.value.code == AIErrorCode.authentication_error


# =====================================================================
# 7. Gateway routing
# =====================================================================

async def test_gateway_routes_to_correct_provider():
    gw = AIGateway()
    mock_adapter = AsyncMock(spec=AIProviderAdapter)
    mock_adapter.generate.return_value = AIResponse(
        request_id="test", provider="mock", model="m", content="ok"
    )
    gw.register("mock_provider", mock_adapter)

    req = AIRequest(provider="mock_provider", messages=[AIMessage(role="user", content="hi")])
    resp = await gw.generate(req)
    assert resp.content == "ok"
    mock_adapter.generate.assert_called_once()


async def test_gateway_unknown_provider():
    gw = AIGateway()
    req = AIRequest(provider="nonexistent", messages=[AIMessage(role="user", content="hi")])
    with pytest.raises(AIError) as exc_info:
        await gw.generate(req)
    assert exc_info.value.code == AIErrorCode.invalid_request


def test_gateway_infer_provider_from_model():
    assert AIGateway._infer_provider("claude-opus-5") == "claude"
    assert AIGateway._infer_provider("gemini-3.5-flash") == "gemini"
    assert AIGateway._infer_provider("qwen-plus") == "qwen"
    assert AIGateway._infer_provider(None) == "gemini"


def test_gateway_list_providers(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    gw = AIGateway()
    providers = gw.list_providers()
    assert "gemini" in providers
    assert "claude" in providers
    assert "qwen" in providers


async def test_gateway_tenant_id_passed_through():
    gw = AIGateway()
    mock_adapter = AsyncMock(spec=AIProviderAdapter)
    mock_adapter.generate.return_value = AIResponse(
        request_id="t", provider="mock", model="m", content="ok"
    )
    gw.register("mock_provider", mock_adapter)

    req = AIRequest(
        tenant_id=42,
        provider="mock_provider",
        messages=[AIMessage(role="user", content="hi")],
    )
    await gw.generate(req)
    called_req = mock_adapter.generate.call_args[0][0]
    assert called_req.tenant_id == 42


async def test_gateway_structured_output():
    gw = AIGateway()
    mock_adapter = AsyncMock(spec=AIProviderAdapter)
    mock_adapter.generate.return_value = AIResponse(
        request_id="t", provider="mock", model="m", content='{"key": "value"}'
    )
    gw.register("mock_provider", mock_adapter)

    req = AIRequest(
        provider="mock_provider",
        messages=[AIMessage(role="user", content="json")],
        structured_output=True,
    )
    resp = await gw.generate(req)
    assert resp.content == '{"key": "value"}'


async def test_gateway_provider_not_configured():
    gw = AIGateway()
    mock_adapter = AsyncMock(spec=AIProviderAdapter)
    mock_adapter.generate.side_effect = AIError(
        AIErrorCode.authentication_error, "mock", "no key"
    )
    gw.register("mock_provider", mock_adapter)

    req = AIRequest(provider="mock_provider", messages=[AIMessage(role="user", content="hi")])
    with pytest.raises(AIError) as exc_info:
        await gw.generate(req)
    assert exc_info.value.code == AIErrorCode.authentication_error


# =====================================================================
# 8. Integration: Alex → Gateway → Mock Provider
# =====================================================================

async def test_alex_uses_gateway(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    mock_response = AIResponse(
        request_id="test",
        provider="gemini",
        model="gemini-3.5-flash",
        content="Hola, soy Alex.",
        usage=AIUsage(input_tokens=10, output_tokens=5, total_tokens=15),
        finish_reason="STOP",
    )

    with patch("services.ai.gateway.ai_gateway") as mock_gw:
        mock_gw.generate = AsyncMock(return_value=mock_response)

        from services.ai_brain_service import AIBrainService

        mock_session = MagicMock()
        mock_tenant = MagicMock()
        mock_tenant.ai_credits = 100
        mock_session.get.return_value = mock_tenant

        result = await AIBrainService.chat_response(
            session=mock_session,
            tenant_id=1,
            history=[],
            new_message="Hola",
            system_instruction="test",
        )

        assert result == "Hola, soy Alex."
        mock_gw.generate.assert_called_once()
        call_req = mock_gw.generate.call_args[0][0]
        assert call_req.provider == "gemini"
        assert call_req.task == "alex_chat"
        assert call_req.tenant_id == 1


# =====================================================================
# 9. Integration: Landing → Gateway → Mock Provider
# =====================================================================

async def test_landing_cascade_claude_first(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")

    valid_landing_json = json.dumps({
        "hero_title": "Test Hero",
        "hero_subtitle": "A subtitle for testing",
        "cta_text": "Buy Now",
        "sections": [
            {"title": "Section 1", "body": "Body text for section one"},
            {"title": "Section 2", "body": "Body text for section two"},
        ],
        "theme": {
            "primary_color": "#FF6600",
            "secondary_color": "#003366",
            "font_family": "Inter",
        }
    })

    mock_response = AIResponse(
        request_id="test",
        provider="claude",
        model="claude-opus-5",
        content=valid_landing_json,
    )

    with patch("services.ai.gateway.ai_gateway") as mock_gw:
        mock_gw.generate = AsyncMock(return_value=mock_response)

        from services.ai_gateway_service import AIGatewayService
        content, provider = await AIGatewayService.generate_landing_content_cascade(
            "Landing para una tienda de zapatos"
        )

        assert provider == "claude"
        assert content.hero_title == "Test Hero"
        mock_gw.generate.assert_called_once()


async def test_landing_cascade_falls_to_gemini(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "fake")

    valid_landing_json = json.dumps({
        "hero_title": "Gemini Hero",
        "hero_subtitle": "Gemini subtitle",
        "cta_text": "Click",
        "sections": [
            {"title": "S1", "body": "Body 1"},
            {"title": "S2", "body": "Body 2"},
        ],
        "theme": {
            "primary_color": "#112233",
            "secondary_color": "#445566",
            "font_family": "Poppins",
        }
    })

    with patch("services.ai.gateway.ai_gateway") as mock_gw:
        mock_gw.generate = AsyncMock(side_effect=AIError(
            AIErrorCode.authentication_error, "claude", "no key"
        ))

        with patch("services.landing_service._call_gemini") as mock_gemini_call:
            mock_gemini_call.return_value = valid_landing_json

            from services.ai_gateway_service import AIGatewayService
            content, provider = await AIGatewayService.generate_landing_content_cascade(
                "Landing test"
            )

            assert provider == "gemini"
            assert content.hero_title == "Gemini Hero"


# =====================================================================
# 10. Logging
# =====================================================================

async def test_gateway_logs_request(caplog):
    import logging
    gw = AIGateway()
    mock_adapter = AsyncMock(spec=AIProviderAdapter)
    mock_adapter.generate.return_value = AIResponse(
        request_id="logtest123", provider="mock", model="m", content="ok",
        usage=AIUsage(total_tokens=5), finish_reason="STOP",
    )
    gw.register("mock_provider", mock_adapter)

    with caplog.at_level(logging.INFO, logger="ai.gateway"):
        req = AIRequest(provider="mock_provider", messages=[AIMessage(role="user", content="hi")])
        await gw.generate(req)

    log_text = caplog.text
    assert "ai.gateway.request" in log_text
    assert "ai.gateway.response" in log_text
    assert "mock_provider" in log_text
