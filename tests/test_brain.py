"""
JARVIS AI — Tests for AI Brain
"""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.brain import (
    AIBrain,
    OllamaLLM,
    OpenAILLM,
    BaseLLM,
    Message,
    LLMResponse,
    BrainResponse,
    JARVIS_SYSTEM_PROMPT,
)
from config import AIConfig


# ── Fixtures ──────────────────────────────────────────────

@pytest.fixture
def ai_config():
    return AIConfig(
        default_model="ollama/llama3",
        fallback_model="ollama/mistral",
        ollama_host="http://localhost:11434",
        openai_api_key="",
        temperature=0.7,
        max_tokens=2048,
        timeout_seconds=30,
    )


@pytest.fixture
def ollama_llm():
    return OllamaLLM(
        model_name="llama3",
        host="http://localhost:11434",
    )


@pytest.fixture
def brain(ai_config):
    return AIBrain(ai_config)


# ── Tests: LLMResponse ───────────────────────────────────

class TestLLMResponse:

    def test_str_representation(self):
        resp = LLMResponse(text="Hello, sir!", model="llama3")
        assert str(resp) == "Hello, sir!"

    def test_fields(self):
        resp = LLMResponse(
            text="result",
            model="gpt-4o",
            tokens_used=150,
            latency_ms=320.5,
        )
        assert resp.model == "gpt-4o"
        assert resp.tokens_used == 150
        assert resp.latency_ms == 320.5


class TestBrainResponse:

    def test_basic(self):
        br = BrainResponse(
            text="Opening Firefox for you, sir.",
            intent="open_app",
            entities={"app_name": "firefox"},
            confidence=0.95,
            model_used="llama3",
        )
        assert br.intent == "open_app"
        assert br.confidence == 0.95
        assert br.entities["app_name"] == "firefox"

    def test_tool_calls(self):
        br = BrainResponse(
            text="Done",
            tool_calls=[{"tool": "open_app", "params": {"app_name": "firefox"}}],
        )
        assert br.tool_calls is not None
        assert br.tool_calls[0]["tool"] == "open_app"


# ── Tests: Message ────────────────────────────────────────

class TestMessage:

    def test_message(self):
        msg = Message(role="user", content="hello")
        assert msg.role == "user"
        assert msg.content == "hello"


# ── Tests: OllamaLLM ─────────────────────────────────────

class TestOllamaLLM:

    def test_init_strips_prefix(self):
        llm = OllamaLLM(model_name="ollama/llama3")
        assert llm.model_name == "llama3"

    def test_init_no_prefix(self):
        llm = OllamaLLM(model_name="mistral")
        assert llm.model_name == "mistral"

    def test_repr(self):
        llm = OllamaLLM(model_name="llama3")
        assert "OllamaLLM" in repr(llm)
        assert "llama3" in repr(llm)

    @pytest.mark.asyncio
    async def test_health_check_unavailable(self):
        """Test health check when Ollama is not running."""
        llm = OllamaLLM(
            model_name="llama3",
            host="http://localhost:99999",  # Wrong port
            timeout=2.0,
        )
        result = await llm.health_check()
        assert result is False
        assert llm.is_available is False
        await llm.close()


# ── Tests: OpenAILLM ─────────────────────────────────────

class TestOpenAILLM:

    def test_init(self):
        llm = OpenAILLM(model_name="gpt-4o-mini", api_key="sk-test")
        assert llm.model_name == "gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_health_check_no_key(self):
        """Test health check with no API key."""
        llm = OpenAILLM(model_name="gpt-4o-mini", api_key="")
        result = await llm.health_check()
        assert result is False
        assert llm.is_available is False


# ── Tests: AIBrain ────────────────────────────────────────

class TestAIBrain:

    def test_init(self, ai_config):
        brain = AIBrain(ai_config)
        assert brain.is_online is False  # Not initialized yet
        assert brain.active_model == "offline"

    def test_status_before_init(self, brain):
        status = brain.status()
        assert status["online"] is False
        assert status["initialized"] is False
        assert status["active_model"] == "offline"

    @pytest.mark.asyncio
    async def test_think_offline(self, brain):
        """Test think() when no backend is available."""
        brain._initialized = True
        response = await brain.think("open firefox")
        assert response.intent == "offline_notice"
        assert response.confidence == 1.0
        assert "offline" in response.text.lower()

    @pytest.mark.asyncio
    async def test_respond_offline(self, brain):
        """Test respond() when no backend is available."""
        brain._initialized = True
        response = await brain.respond("hello")
        assert "offline" in response.lower()

    @pytest.mark.asyncio
    async def test_summarize_offline(self, brain):
        """Test summarize() fallback when offline."""
        brain._initialized = True
        text = "A" * 500
        result = await brain.summarize(text, max_length=100)
        assert len(result) <= 103  # 100 + "..."

    def test_parse_json_clean(self, brain):
        """Test JSON parsing with clean input."""
        text = '{"intent": "open_app", "confidence": 0.9}'
        result = brain._parse_json_response(text)
        assert result["intent"] == "open_app"
        assert result["confidence"] == 0.9

    def test_parse_json_with_code_block(self, brain):
        """Test JSON parsing from markdown code block."""
        text = '```json\n{"intent": "web_search", "query": "test"}\n```'
        result = brain._parse_json_response(text)
        assert result["intent"] == "web_search"

    def test_parse_json_embedded(self, brain):
        """Test JSON parsing when embedded in text."""
        text = 'Here is the result: {"intent": "greet", "response": "hello"} Done.'
        result = brain._parse_json_response(text)
        assert result["intent"] == "greet"

    def test_parse_json_invalid(self, brain):
        """Test JSON parsing with completely invalid input."""
        text = "This is not JSON at all"
        result = brain._parse_json_response(text)
        assert result["intent"] == "conversation"
        assert result["is_conversational"] is True

    @pytest.mark.asyncio
    async def test_think_with_mock_backend(self, ai_config):
        """Test think() with a mocked LLM backend."""
        brain = AIBrain(ai_config)
        brain._initialized = True

        # Create a mock backend
        mock_backend = AsyncMock(spec=BaseLLM)
        mock_backend.model_name = "mock-model"
        mock_backend.is_available = True

        mock_backend.generate.return_value = LLMResponse(
            text=json.dumps({
                "intent": "open_app",
                "entities": {"app_name": "firefox"},
                "tool_name": "open_app",
                "tool_params": {"app_name": "firefox"},
                "response": "Opening Firefox for you, sir.",
                "confidence": 0.95,
                "is_conversational": False,
            }),
            model="mock-model",
            tokens_used=50,
            latency_ms=100,
        )

        brain._default_backend = mock_backend

        response = await brain.think("open firefox")

        assert response.intent == "open_app"
        assert response.confidence == 0.95
        assert response.entities["app_name"] == "firefox"
        assert response.tool_calls is not None
        assert response.tool_calls[0]["tool"] == "open_app"
        assert response.model_used == "mock-model"
        assert "Firefox" in response.text

    @pytest.mark.asyncio
    async def test_think_fallback(self, ai_config):
        """Test that think() falls back to secondary backend."""
        brain = AIBrain(ai_config)
        brain._initialized = True

        # Primary backend that fails
        failing_backend = AsyncMock(spec=BaseLLM)
        failing_backend.model_name = "primary"
        failing_backend.generate.side_effect = Exception("Primary down!")

        # Fallback backend that works
        fallback_backend = AsyncMock(spec=BaseLLM)
        fallback_backend.model_name = "fallback"
        fallback_backend.generate.return_value = LLMResponse(
            text='{"intent": "greeting", "response": "Hello!", "confidence": 0.8}',
            model="fallback",
        )

        brain._default_backend = failing_backend
        brain._fallback_backend = fallback_backend

        response = await brain.think("hello")

        assert response.intent == "greeting"
        assert response.model_used == "fallback"
        fallback_backend.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_respond_with_mock(self, ai_config):
        """Test respond() with a mocked backend."""
        brain = AIBrain(ai_config)
        brain._initialized = True

        mock_backend = AsyncMock(spec=BaseLLM)
        mock_backend.model_name = "mock-model"
        mock_backend.is_available = True
        mock_backend.chat.return_value = LLMResponse(
            text="Good evening, sir. How can I assist you?",
            model="mock-model",
        )
        brain._default_backend = mock_backend

        response = await brain.respond("hello jarvis")

        assert "sir" in response.lower() or "assist" in response.lower()
        mock_backend.chat.assert_called_once()

    def test_system_prompt(self):
        """Verify JARVIS system prompt contains key elements."""
        assert "JARVIS" in JARVIS_SYSTEM_PROMPT
        assert "Iron Man" in JARVIS_SYSTEM_PROMPT
        assert "sir" in JARVIS_SYSTEM_PROMPT

    @pytest.mark.asyncio
    async def test_close(self, brain):
        """Test closing all backends."""
        mock = AsyncMock(spec=BaseLLM)
        mock.close = AsyncMock()
        brain._backends["test"] = mock

        await brain.close()
        mock.close.assert_called_once()
