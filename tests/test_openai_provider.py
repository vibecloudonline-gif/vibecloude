import os
os.environ["SECRET_KEY"] = "testsecretkey123"
os.environ["VIBECLOUD_API_KEY"] = "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI="

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.ai.contracts import AIMessage, AIRequest, AIResponse, AIError, AIErrorCode
from services.ai.providers.openai_provider import OpenAIAdapter
from services.ai.gateway import AIGateway


def test_openai_adapter_validate_config_no_key():
    adapter = OpenAIAdapter(api_key="")
    assert adapter.validate_config() is False


def test_openai_adapter_validate_config_with_key():
    adapter = OpenAIAdapter(api_key="sk-test-key")
    assert adapter.validate_config() is True


def test_openai_adapter_provider_name():
    adapter = OpenAIAdapter(api_key="sk-test")
    assert adapter.provider_name == "openai"


@pytest.mark.asyncio
async def test_openai_adapter_no_key_raises():
    adapter = OpenAIAdapter(api_key="")
    request = AIRequest(messages=[AIMessage(role="user", content="hola")])
    with pytest.raises(AIError) as exc_info:
        await adapter.generate(request)
    assert exc_info.value.code == AIErrorCode.authentication_error


@pytest.mark.asyncio
async def test_openai_adapter_generate_success():
    adapter = OpenAIAdapter(api_key="sk-test-key")
    request = AIRequest(
        messages=[AIMessage(role="user", content="Hola")],
        system_prompt="Sos un asistente",
        model="gpt-4o",
    )

    mock_choice = MagicMock()
    mock_choice.message.content = "Hola, soy GPT-4o"
    mock_choice.message.tool_calls = None
    mock_choice.finish_reason = "stop"

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 10
    mock_usage.completion_tokens = 5
    mock_usage.total_tokens = 15

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage

    mock_client_instance = AsyncMock()
    mock_client_instance.chat.completions.create = AsyncMock(return_value=mock_response)
    mock_client_instance.close = AsyncMock()

    with patch("openai.AsyncOpenAI", return_value=mock_client_instance):
        response = await adapter.generate(request)

    assert isinstance(response, AIResponse)
    assert response.provider == "openai"
    assert response.model == "gpt-4o"
    assert response.content == "Hola, soy GPT-4o"
    assert response.usage.total_tokens == 15
    assert response.finish_reason == "stop"


@pytest.mark.asyncio
async def test_openai_adapter_tool_calls():
    adapter = OpenAIAdapter(api_key="sk-test-key")
    request = AIRequest(
        messages=[AIMessage(role="user", content="cuanto stock hay?")],
        tools=[{"function_declarations": [{"name": "consultar_stock", "description": "Consulta stock", "parameters": {"type": "object", "properties": {}}}]}],
    )

    mock_tc = MagicMock()
    mock_tc.function.name = "consultar_stock"
    mock_tc.function.arguments = '{"product": "zapatos"}'
    mock_tc.id = "call_123"

    mock_choice = MagicMock()
    mock_choice.message.content = None
    mock_choice.message.tool_calls = [mock_tc]
    mock_choice.finish_reason = "tool_calls"

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = MagicMock(prompt_tokens=20, completion_tokens=10, total_tokens=30)

    mock_client_instance = AsyncMock()
    mock_client_instance.chat.completions.create = AsyncMock(return_value=mock_response)
    mock_client_instance.close = AsyncMock()

    with patch("openai.AsyncOpenAI", return_value=mock_client_instance):
        response = await adapter.generate(request)

    assert len(response.tool_calls) == 1
    assert response.tool_calls[0]["name"] == "consultar_stock"
    assert response.tool_calls[0]["args"]["product"] == "zapatos"


def test_gateway_registers_openai():
    gw = AIGateway()
    providers = gw.list_providers()
    assert "openai" in providers


def test_gateway_infer_provider_openai():
    assert AIGateway._infer_provider("gpt-4o") == "openai"
    assert AIGateway._infer_provider("gpt-4o-mini") == "openai"
    assert AIGateway._infer_provider("o1-preview") == "openai"
    assert AIGateway._infer_provider("o3-mini") == "openai"


def test_gateway_infer_provider_others_unchanged():
    assert AIGateway._infer_provider("claude-opus-5") == "claude"
    assert AIGateway._infer_provider("gemini-2.5-flash") == "gemini"
    assert AIGateway._infer_provider("qwen-plus") == "qwen"
    assert AIGateway._infer_provider(None) == "gemini"


def test_convert_tools_gemini_to_openai():
    gemini_tools = [{"function_declarations": [
        {"name": "get_stock", "description": "Gets stock", "parameters": {"type": "object", "properties": {"product": {"type": "string"}}}}
    ]}]
    result = OpenAIAdapter._convert_tools(gemini_tools)
    assert len(result) == 1
    assert result[0]["type"] == "function"
    assert result[0]["function"]["name"] == "get_stock"


def test_convert_tools_already_openai_format():
    openai_tools = [{"type": "function", "function": {"name": "search", "description": "Search", "parameters": {}}}]
    result = OpenAIAdapter._convert_tools(openai_tools)
    assert len(result) == 1
    assert result[0]["function"]["name"] == "search"
