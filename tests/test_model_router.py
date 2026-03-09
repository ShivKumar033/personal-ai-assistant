"""
JARVIS AI — Tests for Model Router
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.model_router import ModelRouter, TaskType, RoutingDecision


@pytest.fixture
def router():
    return ModelRouter()


class TestTaskClassification:
    """Test keyword-based task classification."""

    def test_command_parsing(self, router):
        assert router.classify_task("open firefox") == TaskType.COMMAND_PARSING
        assert router.classify_task("close terminal") == TaskType.COMMAND_PARSING
        assert router.classify_task("start burpsuite") == TaskType.COMMAND_PARSING
        assert router.classify_task("run the script") == TaskType.COMMAND_PARSING
        assert router.classify_task("delete old files") == TaskType.COMMAND_PARSING

    def test_research(self, router):
        assert router.classify_task("search for python tutorials") == TaskType.RESEARCH
        assert router.classify_task("what is kubernetes") == TaskType.RESEARCH
        assert router.classify_task("latest news about AI") == TaskType.RESEARCH
        assert router.classify_task("explain quantum computing") == TaskType.RESEARCH

    def test_code_generation(self, router):
        assert router.classify_task("write code for a web scraper") == TaskType.CODE_GENERATION
        assert router.classify_task("generate a python function") == TaskType.CODE_GENERATION
        assert router.classify_task("debug this code") == TaskType.CODE_GENERATION

    def test_summarization(self, router):
        assert router.classify_task("summarize this article") == TaskType.SUMMARIZATION
        assert router.classify_task("give me the tldr") == TaskType.SUMMARIZATION
        assert router.classify_task("key points of the meeting") == TaskType.SUMMARIZATION

    def test_analysis(self, router):
        assert router.classify_task("analyze this log file") == TaskType.ANALYSIS
        assert router.classify_task("compare these two options") == TaskType.ANALYSIS

    def test_conversation_default(self, router):
        assert router.classify_task("hello jarvis") == TaskType.CONVERSATION
        assert router.classify_task("how are you") == TaskType.CONVERSATION
        assert router.classify_task("good morning") == TaskType.CONVERSATION


class TestModelRouting:
    """Test routing decisions."""

    def test_select_preferred_backend(self, router):
        router.update_availability({"ollama": True, "openai": True})

        decision = router.select(TaskType.COMMAND_PARSING)
        assert decision.backend_name == "ollama"
        assert decision.is_fallback is False

    def test_select_fallback_when_preferred_unavailable(self, router):
        router.update_availability({"ollama": False, "openai": True})

        decision = router.select(TaskType.COMMAND_PARSING)
        assert decision.backend_name == "openai"
        assert decision.is_fallback is True

    def test_select_any_backend_when_both_unavailable(self, router):
        router.update_availability(
            {"ollama": False, "openai": False, "ollama_fallback": True}
        )

        decision = router.select(TaskType.COMMAND_PARSING)
        assert decision.backend_name == "ollama_fallback"
        assert decision.is_fallback is True

    def test_select_none_when_nothing_available(self, router):
        router.update_availability({"ollama": False, "openai": False})

        decision = router.select(TaskType.COMMAND_PARSING)
        assert decision.backend_name == "none"
        assert decision.is_fallback is True

    def test_research_prefers_openai(self, router):
        router.update_availability({"ollama": True, "openai": True})

        decision = router.select(TaskType.RESEARCH)
        assert decision.backend_name == "openai"

    def test_code_gen_prefers_ollama(self, router):
        router.update_availability({"ollama": True, "openai": True})

        decision = router.select(TaskType.CODE_GENERATION)
        assert decision.backend_name == "ollama"

    def test_string_task_type(self, router):
        router.update_availability({"ollama": True})

        decision = router.select("command_parsing")
        assert decision.task_type == TaskType.COMMAND_PARSING

    def test_invalid_task_type_defaults_to_conversation(self, router):
        router.update_availability({"ollama": True})

        decision = router.select("nonexistent_type")
        assert decision.task_type == TaskType.CONVERSATION

    def test_temperature_and_tokens(self, router):
        router.update_availability({"ollama": True})

        decision = router.select(TaskType.COMMAND_PARSING)
        assert decision.temperature == 0.3  # Low temp for commands
        assert decision.max_tokens == 1024

        decision = router.select(TaskType.CREATIVE)
        assert decision.temperature == 0.9  # High temp for creativity
        assert decision.max_tokens == 2048


class TestRoutingDecision:

    def test_str(self):
        rd = RoutingDecision(
            backend_name="ollama",
            task_type=TaskType.COMMAND_PARSING,
            temperature=0.3,
            max_tokens=1024,
            reason="test",
        )
        assert "ollama" in str(rd)
        assert "command_parsing" in str(rd)

    def test_fallback_str(self):
        rd = RoutingDecision(
            backend_name="openai",
            task_type=TaskType.RESEARCH,
            temperature=0.5,
            max_tokens=4096,
            reason="test",
            is_fallback=True,
        )
        assert "(fallback)" in str(rd)


class TestRouterInfo:

    def test_get_rules(self, router):
        rules = router.get_rules()
        assert len(rules) == 8  # 8 task types
        assert all("task_type" in r for r in rules)
        assert all("preferred" in r for r in rules)
        assert all("fallback" in r for r in rules)
