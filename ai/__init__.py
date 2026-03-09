"""
JARVIS AI — AI Package

Provides the reasoning and intelligence layer:
- AIBrain: Central LLM orchestrator
- ModelRouter: Task-based model selection
- BaseLLM, OllamaLLM, OpenAILLM: LLM backends
"""

from ai.brain import (
    AIBrain,
    BaseLLM,
    OllamaLLM,
    OpenAILLM,
    BrainResponse,
    LLMResponse,
    Message,
    JARVIS_SYSTEM_PROMPT,
)
from ai.model_router import ModelRouter, TaskType, RoutingDecision

__all__ = [
    "AIBrain",
    "BaseLLM",
    "OllamaLLM",
    "OpenAILLM",
    "BrainResponse",
    "LLMResponse",
    "Message",
    "ModelRouter",
    "TaskType",
    "RoutingDecision",
    "JARVIS_SYSTEM_PROMPT",
]
