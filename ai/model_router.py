"""
JARVIS AI — Model Router

Intelligently routes tasks to the most appropriate LLM backend
based on task type, resource availability, and performance.

Usage:
    from ai.model_router import ModelRouter
    router = ModelRouter(ai_config)
    backend = router.select(task_type="command_parsing")
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from loguru import logger


class TaskType(str, Enum):
    """Categories of tasks that can be routed to different models."""
    COMMAND_PARSING = "command_parsing"
    CONVERSATION = "conversation"
    RESEARCH = "research"
    CODE_GENERATION = "code_generation"
    SUMMARIZATION = "summarization"
    ANALYSIS = "analysis"
    CREATIVE = "creative"
    TRANSLATION = "translation"


@dataclass
class RoutingRule:
    """A rule mapping a task type to a preferred model/backend."""
    task_type: TaskType
    preferred_backend: str       # "ollama" | "openai" | "ollama_fallback"
    fallback_backend: str        # backup if preferred is unavailable
    reason: str                  # why this routing makes sense
    max_tokens: int = 2048
    temperature: float = 0.7


# ── Default Routing Rules ─────────────────────────────────

DEFAULT_RULES: list[RoutingRule] = [
    RoutingRule(
        task_type=TaskType.COMMAND_PARSING,
        preferred_backend="ollama",
        fallback_backend="openai",
        reason="Fast, private, low-latency for command interpretation",
        max_tokens=1024,
        temperature=0.3,
    ),
    RoutingRule(
        task_type=TaskType.CONVERSATION,
        preferred_backend="ollama",
        fallback_backend="openai",
        reason="Privacy-first for general conversation",
        max_tokens=2048,
        temperature=0.7,
    ),
    RoutingRule(
        task_type=TaskType.RESEARCH,
        preferred_backend="openai",
        fallback_backend="ollama",
        reason="Cloud models have better world knowledge for research",
        max_tokens=4096,
        temperature=0.5,
    ),
    RoutingRule(
        task_type=TaskType.CODE_GENERATION,
        preferred_backend="ollama",
        fallback_backend="openai",
        reason="Local model for code privacy, avoid sending code to cloud",
        max_tokens=4096,
        temperature=0.2,
    ),
    RoutingRule(
        task_type=TaskType.SUMMARIZATION,
        preferred_backend="ollama",
        fallback_backend="openai",
        reason="Local model sufficient for summarization, saves API cost",
        max_tokens=1024,
        temperature=0.3,
    ),
    RoutingRule(
        task_type=TaskType.ANALYSIS,
        preferred_backend="openai",
        fallback_backend="ollama",
        reason="Cloud models have better analytical reasoning",
        max_tokens=4096,
        temperature=0.4,
    ),
    RoutingRule(
        task_type=TaskType.CREATIVE,
        preferred_backend="openai",
        fallback_backend="ollama",
        reason="Cloud models produce better creative content",
        max_tokens=2048,
        temperature=0.9,
    ),
    RoutingRule(
        task_type=TaskType.TRANSLATION,
        preferred_backend="openai",
        fallback_backend="ollama",
        reason="Cloud models have broader language support",
        max_tokens=2048,
        temperature=0.3,
    ),
]


class ModelRouter:
    """
    Intelligent model routing system.

    Routes tasks to the most appropriate LLM backend based on:
    - Task type (command_parsing → local, research → cloud)
    - Backend availability
    - Configuration preferences

    The routing strategy is:
    1. Check the routing rule for the task type
    2. Try the preferred backend
    3. Fall back to the fallback backend
    4. Use whatever is available as last resort
    """

    def __init__(self, ai_config=None) -> None:
        self._rules: dict[TaskType, RoutingRule] = {
            r.task_type: r for r in DEFAULT_RULES
        }
        self._available_backends: set[str] = set()
        self._config = ai_config
        logger.debug(
            f"ModelRouter initialized with {len(self._rules)} routing rules"
        )

    def update_availability(self, backends: dict[str, bool]) -> None:
        """
        Update which backends are currently available.

        Args:
            backends: Dict of backend_name → is_available
        """
        self._available_backends = {
            name for name, available in backends.items() if available
        }
        logger.debug(
            f"Backend availability updated: {self._available_backends}"
        )

    def select(self, task_type: TaskType | str) -> RoutingDecision:
        """
        Select the best backend for a given task type.

        Args:
            task_type: The type of task to route

        Returns:
            RoutingDecision with backend name and parameters
        """
        if isinstance(task_type, str):
            try:
                task_type = TaskType(task_type)
            except ValueError:
                task_type = TaskType.CONVERSATION

        rule = self._rules.get(task_type, self._rules[TaskType.CONVERSATION])

        # Try preferred backend first
        if rule.preferred_backend in self._available_backends:
            return RoutingDecision(
                backend_name=rule.preferred_backend,
                task_type=task_type,
                temperature=rule.temperature,
                max_tokens=rule.max_tokens,
                reason=rule.reason,
                is_fallback=False,
            )

        # Try fallback
        if rule.fallback_backend in self._available_backends:
            logger.info(
                f"Preferred backend '{rule.preferred_backend}' unavailable "
                f"for {task_type.value}, using fallback '{rule.fallback_backend}'"
            )
            return RoutingDecision(
                backend_name=rule.fallback_backend,
                task_type=task_type,
                temperature=rule.temperature,
                max_tokens=rule.max_tokens,
                reason=f"Fallback: {rule.reason}",
                is_fallback=True,
            )

        # Use any available backend
        if self._available_backends:
            any_backend = next(iter(self._available_backends))
            logger.warning(
                f"No preferred/fallback available for {task_type.value}, "
                f"using '{any_backend}'"
            )
            return RoutingDecision(
                backend_name=any_backend,
                task_type=task_type,
                temperature=rule.temperature,
                max_tokens=rule.max_tokens,
                reason="Last resort — using any available backend",
                is_fallback=True,
            )

        # Nothing available
        return RoutingDecision(
            backend_name="none",
            task_type=task_type,
            temperature=rule.temperature,
            max_tokens=rule.max_tokens,
            reason="No backends available",
            is_fallback=True,
        )

    def classify_task(self, user_input: str) -> TaskType:
        """
        Classify user input into a task type using keyword heuristics.

        This is a fast, local classification (no LLM needed).
        """
        text = user_input.lower().strip()

        # ── Command / Action patterns ─────────────────
        action_keywords = [
            "open", "close", "start", "stop", "run", "execute",
            "move", "copy", "delete", "create", "organize",
            "install", "update", "kill", "restart",
        ]
        if any(text.startswith(kw) for kw in action_keywords):
            return TaskType.COMMAND_PARSING

        # ── Research patterns ─────────────────────────
        research_keywords = [
            "search", "find", "look up", "research", "what is",
            "who is", "explain", "latest", "news about",
        ]
        if any(kw in text for kw in research_keywords):
            return TaskType.RESEARCH

        # ── Code patterns ─────────────────────────────
        code_keywords = [
            "write code", "generate code", "implement", "function",
            "script", "program", "debug", "fix this code",
            "python", "javascript", "refactor",
        ]
        if any(kw in text for kw in code_keywords):
            return TaskType.CODE_GENERATION

        # ── Summarization patterns ────────────────────
        summary_keywords = [
            "summarize", "summary", "tldr", "condense",
            "key points", "brief",
        ]
        if any(kw in text for kw in summary_keywords):
            return TaskType.SUMMARIZATION

        # ── Analysis patterns ─────────────────────────
        analysis_keywords = [
            "analyze", "analysis", "compare", "evaluate",
            "assess", "review", "audit",
        ]
        if any(kw in text for kw in analysis_keywords):
            return TaskType.ANALYSIS

        # ── Default to conversation ───────────────────
        return TaskType.CONVERSATION

    def get_rules(self) -> list[dict]:
        """Return all routing rules as dicts."""
        return [
            {
                "task_type": r.task_type.value,
                "preferred": r.preferred_backend,
                "fallback": r.fallback_backend,
                "reason": r.reason,
            }
            for r in self._rules.values()
        ]


@dataclass
class RoutingDecision:
    """Result of a model routing decision."""
    backend_name: str
    task_type: TaskType
    temperature: float
    max_tokens: int
    reason: str
    is_fallback: bool = False

    def __str__(self) -> str:
        fb = " (fallback)" if self.is_fallback else ""
        return f"{self.backend_name}{fb} for {self.task_type.value}"
