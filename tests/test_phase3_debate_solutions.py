import os
os.environ["SECRET_KEY"] = "testsecretkey123"
os.environ["VIBECLOUD_API_KEY"] = "I9StON-hofzi783VWEhFYFM1DCXGJc08SBE1olJhDqI="

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from database.models import DebateObjection, ValidationDebate


def test_debate_persona_prompt_includes_solution():
    from services.debate_service import _DEBATE_PERSONAS

    for persona in _DEBATE_PERSONAS:
        role_lower = persona["role"].lower()
        has_action = any(
            word in role_lower for word in ["solucion", "propone", "propone como"]
        )
        assert has_action, (
            f"Persona {persona['id']} does not propose solutions in role"
        )


def test_debate_objection_has_proposed_solution_field():
    obj = DebateObjection(
        debate_id=1,
        objection_text="Test",
        objection_source="devil_advocate",
        proposed_solution="Ajustar el modelo de negocio",
    )
    assert obj.proposed_solution == "Ajustar el modelo de negocio"


def test_debate_objection_proposed_solution_default_none():
    obj = DebateObjection(
        debate_id=1,
        objection_text="Test",
        objection_source="devil_advocate",
    )
    assert obj.proposed_solution is None


def test_validation_debate_has_action_plan_json():
    debate = ValidationDebate(offer_id=1, status="completed")
    assert hasattr(debate, "action_plan_json")

    plan = ["Paso 1", "Paso 2", "Paso 3"]
    debate.action_plan_json = json.dumps(plan, ensure_ascii=False)
    parsed = json.loads(debate.action_plan_json)
    assert len(parsed) == 3
    assert parsed[0] == "Paso 1"


@pytest.mark.asyncio
async def test_explain_results_returns_none_without_openai():
    with patch("services.ai.gateway.ai_gateway") as mock_gw:
        mock_adapter = MagicMock()
        mock_adapter.validate_config.return_value = False
        mock_gw.get_adapter.return_value = mock_adapter

        from services.ai_gateway_service import AIGatewayService

        result = await AIGatewayService.explain_results(
            {"score": 75, "veredicto": "alto potencial"}, "viability"
        )
        assert result is None


@pytest.mark.asyncio
async def test_explain_results_calls_openai_when_available():
    with patch("services.ai.gateway.ai_gateway") as mock_gw:
        mock_adapter = MagicMock()
        mock_adapter.validate_config.return_value = True
        mock_gw.get_adapter.return_value = mock_adapter

        mock_response = MagicMock()
        mock_response.content = "Tu producto tiene buenas chances de vender bien."
        mock_gw.generate = AsyncMock(return_value=mock_response)

        from services.ai_gateway_service import AIGatewayService

        result = await AIGatewayService.explain_results(
            {"score": 75, "veredicto": "alto potencial"}, "viability"
        )
        assert result is not None
        assert "buenas chances" in result
        mock_gw.generate.assert_called_once()
        call_args = mock_gw.generate.call_args[0][0]
        assert call_args.provider == "openai"
        assert call_args.model == "gpt-4o"


@pytest.mark.asyncio
async def test_explain_results_graceful_on_error():
    with patch("services.ai.gateway.ai_gateway") as mock_gw:
        mock_adapter = MagicMock()
        mock_adapter.validate_config.return_value = True
        mock_gw.get_adapter.return_value = mock_adapter
        mock_gw.generate = AsyncMock(side_effect=Exception("API error"))

        from services.ai_gateway_service import AIGatewayService

        result = await AIGatewayService.explain_results(
            {"score": 50}, "general"
        )
        assert result is None


def test_explain_results_context_types():
    from services.ai_gateway_service import AIGatewayService

    method = AIGatewayService.explain_results
    assert callable(method)


@pytest.mark.asyncio
async def test_persona_agent_parses_proposed_solution():
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "objection": "El precio es muy alto",
        "severity": "high",
        "proposed_solution": "Bajar el precio un 20%",
    })

    with patch("services.ai.gateway.ai_gateway") as mock_gw:
        mock_gw.generate = AsyncMock(return_value=mock_response)

        from services.debate_service import _run_persona_agent, _DEBATE_PERSONAS

        result = await _run_persona_agent(
            _DEBATE_PERSONAS[1],
            "Oferta: Producto X a $100",
        )
        assert result is not None
        assert result["proposed_solution"] == "Bajar el precio un 20%"
        assert result["source"] == "price_skeptic"


@pytest.mark.asyncio
async def test_arbiter_parses_action_plan():
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "resolutions": [
            {"index": 1, "status": "resolved", "text": "Ajustar precio"},
        ],
        "action_plan": [
            "Reducir precio un 15%",
            "Agregar diferenciador",
            "Hacer test A/B",
        ],
        "verdict": "needs_revision",
        "summary": "La oferta necesita ajustes de precio",
    })

    with patch("services.ai.gateway.ai_gateway") as mock_gw:
        mock_gw.generate = AsyncMock(return_value=mock_response)

        from services.debate_service import _run_arbiter

        result = await _run_arbiter(
            "Oferta test",
            [{"source": "price_skeptic", "severity": "high",
              "objection": "Muy caro", "proposed_solution": "Bajar precio"}],
        )
        assert result is not None
        assert len(result["action_plan"]) == 3
        assert "Reducir precio" in result["action_plan"][0]
