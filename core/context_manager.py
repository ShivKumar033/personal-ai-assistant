"""
JARVIS AI — Context Manager

Tracks conversation context, session state, and provides
context windows for LLM prompts.

Usage:
    from core.context_manager import ContextManager
    ctx = ContextManager(max_history=50)
    ctx.add_exchange("open firefox", "Opening Firefox for you.")
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger


@dataclass
class Exchange:
    """A single user ↔ JARVIS exchange."""
    user_input: str
    jarvis_response: str
    intent: Optional[str] = None
    entities: Optional[dict] = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    success: bool = True


class ContextManager:
    """
    Manages conversational context and session metadata.

    Stores:
    - Conversation history (last N exchanges)
    - Current session variables
    - Active window / application info
    - Running agent references
    """

    def __init__(self, max_history: int = 50) -> None:
        self._history: deque[Exchange] = deque(maxlen=max_history)
        self._session_vars: dict[str, Any] = {}
        self._active_agents: dict[str, str] = {}
        self._current_topic: Optional[str] = None
        self._max_history = max_history

        logger.debug(f"ContextManager initialized (max_history={max_history})")

    # ── Conversation History ──────────────────────────────

    def add_exchange(
        self,
        user_input: str,
        jarvis_response: str,
        intent: Optional[str] = None,
        entities: Optional[dict] = None,
        success: bool = True,
    ) -> None:
        """Record a user ↔ JARVIS exchange."""
        exchange = Exchange(
            user_input=user_input,
            jarvis_response=jarvis_response,
            intent=intent,
            entities=entities,
            success=success,
        )
        self._history.append(exchange)
        logger.debug(
            f"Exchange recorded: '{user_input[:50]}...' "
            f"→ intent={intent}"
        )

    @property
    def history(self) -> list[Exchange]:
        """Get full conversation history."""
        return list(self._history)

    @property
    def last_exchange(self) -> Optional[Exchange]:
        """Get last exchange."""
        return self._history[-1] if self._history else None

    def get_recent(self, n: int = 5) -> list[Exchange]:
        """Get last N exchanges."""
        items = list(self._history)
        return items[-n:] if len(items) >= n else items

    def build_prompt_context(self, max_exchanges: int = 10) -> str:
        """
        Build a context string for LLM prompts from recent history.

        Returns a formatted string of recent exchanges for injection
        into the LLM system/user prompt.
        """
        recent = self.get_recent(max_exchanges)
        if not recent:
            return "No previous conversation context."

        lines = ["Previous conversation:"]
        for ex in recent:
            lines.append(f"  User: {ex.user_input}")
            lines.append(f"  JARVIS: {ex.jarvis_response}")
            if ex.intent:
                lines.append(f"  [Intent: {ex.intent}]")
            lines.append("")
        return "\n".join(lines)

    # ── Session Variables ─────────────────────────────────

    def set_var(self, key: str, value: Any) -> None:
        """Set a session variable."""
        self._session_vars[key] = value

    def get_var(self, key: str, default: Any = None) -> Any:
        """Get a session variable."""
        return self._session_vars.get(key, default)

    def del_var(self, key: str) -> None:
        """Delete a session variable."""
        self._session_vars.pop(key, None)

    # ── Topic Tracking ────────────────────────────────────

    @property
    def current_topic(self) -> Optional[str]:
        return self._current_topic

    @current_topic.setter
    def current_topic(self, topic: str) -> None:
        self._current_topic = topic
        logger.debug(f"Topic set: {topic}")

    # ── Agent Tracking ────────────────────────────────────

    def register_agent(self, agent_id: str, agent_type: str) -> None:
        """Register an active agent."""
        self._active_agents[agent_id] = agent_type
        logger.debug(f"Agent registered: {agent_id} ({agent_type})")

    def unregister_agent(self, agent_id: str) -> None:
        """Remove an agent from tracking."""
        self._active_agents.pop(agent_id, None)

    @property
    def active_agents(self) -> dict[str, str]:
        return dict(self._active_agents)

    # ── Housekeeping ──────────────────────────────────────

    def clear(self) -> None:
        """Clear all context (for new session)."""
        self._history.clear()
        self._session_vars.clear()
        self._active_agents.clear()
        self._current_topic = None
        logger.info("Context cleared")

    def summary(self) -> dict:
        """Context summary for status display."""
        return {
            "history_length": len(self._history),
            "max_history": self._max_history,
            "session_vars": len(self._session_vars),
            "active_agents": len(self._active_agents),
            "current_topic": self._current_topic,
            "last_exchange": (
                self.last_exchange.user_input[:60]
                if self.last_exchange
                else None
            ),
        }
