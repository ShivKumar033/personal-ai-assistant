"""
JARVIS AI — Command Interpreter

Converts natural language input into structured commands
by combining keyword heuristics with LLM-powered intent extraction.

Usage:
    from core.command_interpreter import CommandInterpreter
    interpreter = CommandInterpreter(brain, tool_registry)
    intent = await interpreter.interpret("open my pentesting workspace")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from loguru import logger


@dataclass
class IntentResult:
    """Structured interpretation of user input."""
    raw_input: str
    intent: str                           # e.g., "open_app", "web_search", "conversation"
    entities: dict[str, Any] = field(default_factory=dict)
    tool_name: Optional[str] = None       # Matched tool (if any)
    tool_params: dict[str, Any] = field(default_factory=dict)
    response_text: str = ""               # JARVIS response
    confidence: float = 0.0
    is_conversational: bool = False       # Pure chat vs action
    model_used: str = ""
    source: str = "unknown"               # "ai" | "keyword" | "direct"


# ── Keyword Patterns for Offline / Fast Intent Detection ──

KEYWORD_PATTERNS: list[dict] = [
    # System controls
    {
        "pattern": r"^(?:open|launch|start|run)\s+(.+)",
        "intent": "open_app",
        "tool": "open_app",
        "entity_key": "app_name",
    },
    {
        "pattern": r"^(?:close|kill|stop|end|quit)\s+(.+)",
        "intent": "close_app",
        "tool": "close_app",
        "entity_key": "app_name",
    },
    # System info queries
    {
        "pattern": r"(?:system\s*info|system\s*status|how(?:'s| is) (?:my )?(?:system|computer))",
        "intent": "system_info",
        "tool": "system_info",
    },
    {
        "pattern": r"(?:what(?:'s| is) (?:the )?time|current time|what time)",
        "intent": "current_time",
        "tool": "current_time",
    },
    {
        "pattern": r"(?:list|show|what)\s+(?:processes|running|apps)",
        "intent": "list_processes",
        "tool": "list_processes",
    },
    {
        "pattern": r"(?:battery|power|charging|charge\s*level)",
        "intent": "battery_info",
        "tool": "battery_info",
    },
    {
        "pattern": r"(?:disk|storage|space|how much (?:disk|storage|space))",
        "intent": "disk_space",
        "tool": "disk_space",
    },
    {
        "pattern": r"(?:network|ip\s*address|interfaces|connectivity)",
        "intent": "network_info",
        "tool": "network_info",
    },
    {
        "pattern": r"(?:uptime|how long|boot\s*time|been running)",
        "intent": "system_uptime",
        "tool": "system_uptime",
    },
    # File operations
    {
        "pattern": r"^(?:organize|sort|clean)\s+(?:my\s+)?(.+?)(?:\s+folder)?$",
        "intent": "organize_folder",
        "tool": "organize_folder",
        "entity_key": "path",
    },
    {
        "pattern": r"^(?:create|make|new)\s+(?:a\s+)?(?:file|document)\s+(?:called\s+)?(.+)",
        "intent": "create_file",
        "tool": "create_file",
        "entity_key": "path",
    },
    {
        "pattern": r"^(?:move|mv)\s+(.+?)\s+(?:to)\s+(.+)",
        "intent": "move_file",
        "tool": "move_file",
        "entity_keys": ["source", "destination"],
    },
    {
        "pattern": r"^(?:delete|remove|rm)\s+(.+)",
        "intent": "delete_file",
        "tool": "delete_file",
        "entity_key": "path",
    },
    # Web actions
    {
        "pattern": r"^(?:search|google|look up|find)\s+(?:for\s+)?(.+)",
        "intent": "web_search",
        "tool": "search_web",
        "entity_key": "query",
    },
    {
        "pattern": r"^(?:browse|go to|open|visit)\s+(https?://\S+)",
        "intent": "open_url",
        "tool": "open_url",
        "entity_key": "url",
    },
]


class CommandInterpreter:
    """
    Interprets natural language commands into structured intents.

    Strategy:
    1. Check for direct tool name match (e.g., "system_info")
    2. Try keyword pattern matching (fast, offline)
    3. Fall back to AI Brain for complex interpretation
    """

    def __init__(self, brain=None, registry=None) -> None:
        """
        Args:
            brain: AIBrain instance for LLM-powered interpretation
            registry: ToolRegistry for tool matching
        """
        self._brain = brain
        self._registry = registry

        # Compile patterns
        self._patterns = [
            {**p, "_compiled": re.compile(p["pattern"], re.IGNORECASE)}
            for p in KEYWORD_PATTERNS
        ]

        logger.debug(
            f"CommandInterpreter initialized with "
            f"{len(self._patterns)} keyword patterns"
        )

    async def interpret(self, user_input: str) -> IntentResult:
        """
        Interpret user input into a structured intent.

        Pipeline:
        1. Direct tool name match
        2. Keyword pattern matching
        3. AI Brain interpretation (if available)
        4. Fallback to conversation
        """
        text = user_input.strip()

        if not text:
            return IntentResult(
                raw_input=text,
                intent="empty",
                response_text="I didn't catch that. Could you say that again?",
                confidence=1.0,
                is_conversational=True,
                source="direct",
            )

        # ── Step 1: Direct tool match ─────────────────
        result = self._try_direct_tool_match(text)
        if result:
            logger.debug(f"Direct tool match: {result.tool_name}")
            return result

        # ── Step 2: Keyword pattern matching ──────────
        result = self._try_keyword_match(text)
        if result:
            logger.debug(
                f"Keyword match: intent={result.intent}, "
                f"tool={result.tool_name}"
            )
            return result

        # ── Step 3: AI Brain interpretation ───────────
        if self._brain and self._brain.is_online:
            result = await self._ai_interpret(text)
            if result:
                logger.debug(
                    f"AI interpretation: intent={result.intent}, "
                    f"confidence={result.confidence:.2f}"
                )
                return result

        # ── Step 4: Fallback — treat as conversation ──
        return IntentResult(
            raw_input=text,
            intent="conversation",
            response_text="",
            confidence=0.3,
            is_conversational=True,
            source="fallback",
        )

    # ── Step 1: Direct Tool Match ─────────────────────────

    def _try_direct_tool_match(self, text: str) -> Optional[IntentResult]:
        """Check if input directly matches a tool name."""
        if not self._registry:
            return None

        parts = text.strip().split(maxsplit=1)
        tool_name = parts[0].lower().replace("-", "_")

        if not self._registry.exists(tool_name):
            return None

        # Parse params
        params = {}
        if len(parts) > 1:
            import json
            try:
                params = json.loads(parts[1])
            except (json.JSONDecodeError, ValueError):
                tool_def = self._registry.get(tool_name)
                if tool_def and tool_def.parameters:
                    first_param = list(tool_def.parameters.keys())[0]
                    params = {first_param: parts[1]}

        return IntentResult(
            raw_input=text,
            intent=tool_name,
            tool_name=tool_name,
            tool_params=params,
            confidence=1.0,
            is_conversational=False,
            source="direct",
        )

    # ── Step 2: Keyword Pattern Matching ──────────────────

    def _try_keyword_match(self, text: str) -> Optional[IntentResult]:
        """Match input against keyword patterns."""
        for pattern_def in self._patterns:
            match = pattern_def["_compiled"].search(text)
            if not match:
                continue

            entities = {}
            params = {}

            # Extract entities from capture groups
            if "entity_key" in pattern_def and match.groups():
                entity_val = match.group(1).strip()
                entities[pattern_def["entity_key"]] = entity_val
                params[pattern_def["entity_key"]] = entity_val
            elif "entity_keys" in pattern_def:
                for i, key in enumerate(pattern_def["entity_keys"], 1):
                    if i <= len(match.groups()):
                        entities[key] = match.group(i).strip()
                        params[key] = match.group(i).strip()

            # Check if the tool actually exists
            tool_name = pattern_def.get("tool")
            if tool_name and self._registry and not self._registry.exists(tool_name):
                # Tool referenced but doesn't exist yet
                tool_name = None

            return IntentResult(
                raw_input=text,
                intent=pattern_def["intent"],
                entities=entities,
                tool_name=tool_name,
                tool_params=params,
                confidence=0.85,
                is_conversational=False,
                source="keyword",
            )

        return None

    # ── Step 3: AI Brain Interpretation ───────────────────

    async def _ai_interpret(self, text: str) -> Optional[IntentResult]:
        """Use the AI Brain for complex interpretation."""
        try:
            # Get tool schemas for the LLM
            tool_schemas = (
                self._registry.get_tool_schemas()
                if self._registry
                else []
            )

            # Get conversation context
            context = ""  # Will be passed by the assistant

            brain_response = await self._brain.think(
                user_input=text,
                available_tools=tool_schemas,
            )

            # Validate tool_name if one was suggested
            tool_name = None
            tool_params = {}
            if brain_response.tool_calls:
                call = brain_response.tool_calls[0]
                suggested_tool = call.get("tool")
                if (
                    suggested_tool
                    and self._registry
                    and self._registry.exists(suggested_tool)
                ):
                    tool_name = suggested_tool
                    tool_params = call.get("params", {})

            is_conv = (
                brain_response.intent in ("conversation", "greeting", "question")
                or tool_name is None
            )

            return IntentResult(
                raw_input=text,
                intent=brain_response.intent or "unknown",
                entities=brain_response.entities or {},
                tool_name=tool_name,
                tool_params=tool_params,
                response_text=brain_response.text,
                confidence=brain_response.confidence,
                is_conversational=is_conv and tool_name is None,
                model_used=brain_response.model_used,
                source="ai",
            )

        except Exception as e:
            logger.error(f"AI interpretation failed: {e}")
            return None

    # ── Utilities ─────────────────────────────────────────

    def get_patterns(self) -> list[dict]:
        """Return supported patterns (for help display)."""
        return [
            {
                "pattern": p["pattern"],
                "intent": p["intent"],
                "tool": p.get("tool"),
            }
            for p in KEYWORD_PATTERNS
        ]
