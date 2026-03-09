"""
JARVIS AI — Tests for Command Interpreter
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.command_interpreter import CommandInterpreter, IntentResult
from tools.tool_registry import ToolRegistry
from ai.brain import AIBrain, BrainResponse


# ── Fixtures ──────────────────────────────────────────────

@pytest.fixture
def registry():
    """Create a ToolRegistry with some test tools."""
    reg = ToolRegistry()

    @reg.register(name="system_info", description="Get system info", category="system")
    async def system_info(): pass

    @reg.register(name="list_processes", description="List processes", category="system")
    async def list_processes(filter_name: str = ""): pass

    @reg.register(name="current_time", description="Get time", category="info")
    async def current_time(): pass

    @reg.register(name="open_app", description="Open an app", category="system")
    async def open_app(app_name: str): pass

    @reg.register(name="search_web", description="Search the web", category="web")
    async def search_web(query: str): pass

    return reg


@pytest.fixture
def interpreter(registry):
    """Create interpreter without AI brain (keyword-only)."""
    return CommandInterpreter(brain=None, registry=registry)


@pytest.fixture
def ai_interpreter(registry):
    """Create interpreter with mocked AI brain."""
    mock_brain = AsyncMock(spec=AIBrain)
    mock_brain.is_online = True
    return CommandInterpreter(brain=mock_brain, registry=registry)


# ── Tests: Direct Tool Matching ──────────────────────────

class TestDirectToolMatch:

    @pytest.mark.asyncio
    async def test_exact_tool_name(self, interpreter):
        result = await interpreter.interpret("system_info")
        assert result.tool_name == "system_info"
        assert result.source == "direct"
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_tool_with_param(self, interpreter):
        result = await interpreter.interpret("list_processes firefox")
        assert result.tool_name == "list_processes"
        assert result.tool_params.get("filter_name") == "firefox"
        assert result.source == "direct"

    @pytest.mark.asyncio
    async def test_tool_with_json_params(self, interpreter):
        result = await interpreter.interpret(
            'open_app {"app_name": "firefox"}'
        )
        assert result.tool_name == "open_app"
        assert result.tool_params.get("app_name") == "firefox"

    @pytest.mark.asyncio
    async def test_tool_with_hyphen(self, interpreter):
        """Test that hyphens are converted to underscores."""
        result = await interpreter.interpret("system-info")
        assert result.tool_name == "system_info"


# ── Tests: Keyword Pattern Matching ──────────────────────

class TestKeywordMatching:

    @pytest.mark.asyncio
    async def test_open_app(self, interpreter):
        result = await interpreter.interpret("open firefox")
        assert result.intent == "open_app"
        assert result.entities.get("app_name") == "firefox"
        assert result.source == "keyword"
        assert result.confidence == 0.85

    @pytest.mark.asyncio
    async def test_launch_app(self, interpreter):
        result = await interpreter.interpret("launch burpsuite")
        assert result.intent == "open_app"
        assert result.entities.get("app_name") == "burpsuite"

    @pytest.mark.asyncio
    async def test_start_app(self, interpreter):
        result = await interpreter.interpret("start terminal")
        assert result.intent == "open_app"
        assert result.entities.get("app_name") == "terminal"

    @pytest.mark.asyncio
    async def test_system_status_query(self, interpreter):
        result = await interpreter.interpret("how is my system")
        assert result.intent == "system_info"
        assert result.source == "keyword"

    @pytest.mark.asyncio
    async def test_time_query(self, interpreter):
        result = await interpreter.interpret("what time is it")
        assert result.intent == "current_time"

    @pytest.mark.asyncio
    async def test_whats_the_time(self, interpreter):
        result = await interpreter.interpret("what's the time")
        assert result.intent == "current_time"

    @pytest.mark.asyncio
    async def test_battery_query(self, interpreter):
        result = await interpreter.interpret("check battery level")
        assert result.intent == "battery_info"

    @pytest.mark.asyncio
    async def test_disk_space(self, interpreter):
        result = await interpreter.interpret("how much disk space do I have")
        assert result.intent == "disk_space"

    @pytest.mark.asyncio
    async def test_network_info(self, interpreter):
        result = await interpreter.interpret("show my ip address")
        assert result.intent == "network_info"

    @pytest.mark.asyncio
    async def test_list_processes(self, interpreter):
        result = await interpreter.interpret("show running processes")
        assert result.intent == "list_processes"

    @pytest.mark.asyncio
    async def test_uptime(self, interpreter):
        result = await interpreter.interpret("how long has the system been running")
        assert result.intent == "system_uptime"

    @pytest.mark.asyncio
    async def test_web_search(self, interpreter):
        result = await interpreter.interpret("search for latest CVEs")
        assert result.intent == "web_search"
        assert result.entities.get("query") == "latest CVEs"

    @pytest.mark.asyncio
    async def test_close_app(self, interpreter):
        result = await interpreter.interpret("close firefox")
        assert result.intent == "close_app"
        assert result.entities.get("app_name") == "firefox"

    @pytest.mark.asyncio
    async def test_case_insensitive(self, interpreter):
        result = await interpreter.interpret("OPEN Firefox")
        assert result.intent == "open_app"
        assert "firefox" in result.entities.get("app_name", "").lower()


# ── Tests: AI Brain Interpretation ───────────────────────

class TestAIInterpretation:

    @pytest.mark.asyncio
    async def test_ai_routes_to_tool(self, ai_interpreter):
        """Test that AI can route to a registered tool."""
        mock_brain = ai_interpreter._brain
        mock_brain.think.return_value = BrainResponse(
            text="I'll check the system info for you, sir.",
            intent="system_check",
            entities={"category": "system"},
            tool_calls=[{"tool": "system_info", "params": {}}],
            confidence=0.92,
            model_used="llama3",
        )

        # Use input that won't match any keyword pattern
        result = await ai_interpreter.interpret(
            "I need to check my workstation health"
        )
        assert result.tool_name == "system_info"
        assert result.source == "ai"
        assert result.confidence == 0.92

    @pytest.mark.asyncio
    async def test_ai_conversational(self, ai_interpreter):
        """Test AI handling a conversational query."""
        mock_brain = ai_interpreter._brain
        mock_brain.think.return_value = BrainResponse(
            text="Hello! I'm JARVIS, your AI assistant.",
            intent="greeting",
            entities={},
            tool_calls=None,
            confidence=0.98,
            model_used="llama3",
        )

        result = await ai_interpreter.interpret("hello jarvis!")
        assert result.is_conversational is True
        assert result.source == "ai"
        assert "JARVIS" in result.response_text

    @pytest.mark.asyncio
    async def test_ai_invalid_tool_rejected(self, ai_interpreter):
        """Test that AI suggesting a non-existent tool is handled."""
        mock_brain = ai_interpreter._brain
        mock_brain.think.return_value = BrainResponse(
            text="Let me play music for you.",
            intent="play_music",
            tool_calls=[{"tool": "play_spotify", "params": {"track": "test"}}],
            confidence=0.7,
            model_used="llama3",
        )

        result = await ai_interpreter.interpret("play some music")
        # play_spotify doesn't exist in registry, so tool_name should be None
        assert result.tool_name is None
        assert result.is_conversational is True

    @pytest.mark.asyncio
    async def test_ai_error_handled(self, ai_interpreter):
        """Test graceful handling of AI errors."""
        mock_brain = ai_interpreter._brain
        mock_brain.think.side_effect = Exception("LLM timeout")

        result = await ai_interpreter.interpret("do something complex")
        # Should fall through to fallback
        assert result.source == "fallback"
        assert result.is_conversational is True


# ── Tests: Fallback Behavior ─────────────────────────────

class TestFallback:

    @pytest.mark.asyncio
    async def test_unrecognized_no_ai(self, interpreter):
        """Test unrecognized input without AI brain."""
        result = await interpreter.interpret(
            "remember to buy groceries tomorrow"
        )
        assert result.source == "fallback"
        assert result.is_conversational is True
        assert result.confidence == 0.3

    @pytest.mark.asyncio
    async def test_empty_input(self, interpreter):
        result = await interpreter.interpret("")
        assert result.intent == "empty"
        assert result.source == "direct"

    @pytest.mark.asyncio
    async def test_whitespace_input(self, interpreter):
        result = await interpreter.interpret("   ")
        assert result.intent == "empty"


# ── Tests: IntentResult ──────────────────────────────────

class TestIntentResult:

    def test_defaults(self):
        result = IntentResult(raw_input="test", intent="test_intent")
        assert result.tool_name is None
        assert result.tool_params == {}
        assert result.entities == {}
        assert result.confidence == 0.0
        assert result.is_conversational is False
        assert result.source == "unknown"

    def test_full_result(self):
        result = IntentResult(
            raw_input="open firefox",
            intent="open_app",
            entities={"app_name": "firefox"},
            tool_name="open_app",
            tool_params={"app_name": "firefox"},
            response_text="Opening Firefox.",
            confidence=0.95,
            is_conversational=False,
            model_used="llama3",
            source="ai",
        )
        assert result.tool_name == "open_app"
        assert result.model_used == "llama3"


# ── Tests: Pattern Discovery ─────────────────────────────

class TestPatterns:

    def test_get_patterns(self, interpreter):
        patterns = interpreter.get_patterns()
        assert len(patterns) > 0
        assert all("pattern" in p for p in patterns)
        assert all("intent" in p for p in patterns)
