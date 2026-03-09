"""
JARVIS AI — Tool Registry

Central registry for all JARVIS tools (actions the AI can perform).
Tools are registered via decorators and discovered automatically.

Usage:
    from tools.tool_registry import ToolRegistry, tool

    registry = ToolRegistry()

    @registry.register(
        name="open_app",
        description="Opens an application by name",
        category="system",
        risk_level="safe"
    )
    async def open_app(app_name: str) -> str:
        ...

    # List all tools
    registry.list_tools()
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

from loguru import logger


@dataclass
class ToolDefinition:
    """Metadata for a registered tool."""
    name: str
    description: str
    category: str
    risk_level: str                          # safe | confirm | blocked
    parameters: dict[str, str]               # param_name → type_hint
    handler: Callable                        # the actual function
    examples: list[str] = field(default_factory=list)
    enabled: bool = True

    def to_dict(self) -> dict:
        """Convert to dict for LLM function-calling schemas."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "risk_level": self.risk_level,
            "parameters": self.parameters,
            "examples": self.examples,
            "enabled": self.enabled,
        }


class ToolRegistry:
    """
    Central catalog of JARVIS tools.

    Provides:
    - Decorator-based tool registration
    - Tool lookup by name or category
    - Tool metadata for LLM function calling
    - Enable/disable tools at runtime
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        logger.debug("ToolRegistry initialized")

    # ── Registration ──────────────────────────────────────

    def register(
        self,
        name: str,
        description: str,
        category: str = "general",
        risk_level: str = "safe",
        examples: Optional[list[str]] = None,
    ) -> Callable:
        """
        Decorator to register a tool function.

        Args:
            name: Unique tool name (e.g., 'open_app')
            description: Human-readable description for the LLM
            category: Tool category ('system', 'file', 'web', etc.)
            risk_level: Permission level ('safe', 'confirm', 'blocked')
            examples: Example usage strings

        Returns:
            Decorator function
        """
        def decorator(func: Callable) -> Callable:
            # Extract parameter info from function signature
            sig = inspect.signature(func)
            params = {}
            for param_name, param in sig.parameters.items():
                if param_name in ("self", "cls"):
                    continue
                ann = param.annotation
                if ann == inspect.Parameter.empty:
                    type_hint = "any"
                elif isinstance(ann, str):
                    # String annotation (e.g., from __future__ annotations)
                    type_hint = ann
                elif hasattr(ann, "__name__"):
                    type_hint = ann.__name__
                else:
                    type_hint = str(ann)
                params[param_name] = type_hint

            tool_def = ToolDefinition(
                name=name,
                description=description,
                category=category,
                risk_level=risk_level,
                parameters=params,
                handler=func,
                examples=examples or [],
            )

            self._tools[name] = tool_def
            logger.debug(
                f"Tool registered: '{name}' [{category}] "
                f"(risk: {risk_level})"
            )
            return func

        return decorator

    def register_tool(self, tool_def: ToolDefinition) -> None:
        """Register a tool directly from a ToolDefinition."""
        self._tools[tool_def.name] = tool_def
        logger.debug(f"Tool registered: '{tool_def.name}'")

    # ── Lookup ────────────────────────────────────────────

    def get(self, name: str) -> Optional[ToolDefinition]:
        """Get a tool by name."""
        return self._tools.get(name)

    def exists(self, name: str) -> bool:
        """Check if a tool exists."""
        return name in self._tools

    def list_tools(self, category: Optional[str] = None) -> list[ToolDefinition]:
        """
        List all registered tools, optionally filtered by category.

        Args:
            category: Filter by category (None = all tools)
        """
        tools = list(self._tools.values())
        if category:
            tools = [t for t in tools if t.category == category]
        return [t for t in tools if t.enabled]

    def list_categories(self) -> list[str]:
        """List all unique tool categories."""
        return list(set(t.category for t in self._tools.values()))

    def get_tool_schemas(self) -> list[dict]:
        """
        Get tool definitions as dicts for LLM function calling.

        Returns:
            List of tool metadata dicts suitable for LLM prompts
        """
        return [
            t.to_dict()
            for t in self._tools.values()
            if t.enabled
        ]

    # ── Management ────────────────────────────────────────

    def enable(self, name: str) -> bool:
        """Enable a tool."""
        if tool := self._tools.get(name):
            tool.enabled = True
            logger.info(f"Tool enabled: '{name}'")
            return True
        return False

    def disable(self, name: str) -> bool:
        """Disable a tool."""
        if tool := self._tools.get(name):
            tool.enabled = False
            logger.info(f"Tool disabled: '{name}'")
            return True
        return False

    def unregister(self, name: str) -> bool:
        """Remove a tool from the registry."""
        if name in self._tools:
            del self._tools[name]
            logger.info(f"Tool unregistered: '{name}'")
            return True
        return False

    # ── Info ──────────────────────────────────────────────

    @property
    def count(self) -> int:
        return len(self._tools)

    def summary(self) -> dict:
        """Registry summary."""
        categories = {}
        for tool in self._tools.values():
            cat = tool.category
            categories[cat] = categories.get(cat, 0) + 1

        return {
            "total_tools": len(self._tools),
            "enabled": sum(1 for t in self._tools.values() if t.enabled),
            "disabled": sum(1 for t in self._tools.values() if not t.enabled),
            "categories": categories,
        }
