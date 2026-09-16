"""AI Gateway — unified entry point for all AI provider calls.

Sub-modules:
- contracts: AIRequest, AIResponse, AIError
- providers/: Adapters for Gemini, Claude, Qwen
- gateway: AIGateway (single entry point)
"""
from services.ai.contracts import AIRequest, AIResponse, AIError, AIErrorCode, AIMessage, AIUsage
from services.ai.gateway import AIGateway

__all__ = [
    "AIRequest", "AIResponse", "AIError", "AIErrorCode",
    "AIMessage", "AIUsage", "AIGateway",
]
