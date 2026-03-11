"""
JARVIS AI — Memory Tools (Phase 6)

Tools for the AI Brain to explicitly remember and recall long-term facts
or user preferences.
"""

from typing import Any, Dict
from loguru import logger


def register_memory_tools(registry, memory_manager) -> None:
    """Register all memory tools."""

    @registry.register(
        name="remember_preference",
        description="Saves a user preference, setting, or important fact permanently.",
        category="memory",
        risk_level="safe"
    )
    async def remember_preference(key: str, value: str) -> str:
        """Saves a user preference or setting to long-term memory."""
        try:
            memory_manager.long_term.set_preference(key, value)
            return f"Preference '{key}' saved successfully: {value}"
        except Exception as e:
            raise Exception(f"Failed to save preference: {e}")

    @registry.register(
        name="recall_preference",
        description="Retrieves a previously saved user preference or setting.",
        category="memory",
        risk_level="safe"
    )
    async def recall_preference(key: str) -> str:
        """Retrieves a previously saved user preference."""
        try:
            value = memory_manager.long_term.get_preference(key)
            if value is not None:
                return f"Retrieved preference for '{key}': {value}"
            else:
                return f"No preference found for key '{key}'"
        except Exception as e:
            raise Exception(f"Failed to recall preference: {e}")

    logger.debug("Memory tools registered.")
