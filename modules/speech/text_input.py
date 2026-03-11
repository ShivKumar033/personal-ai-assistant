"""
JARVIS AI — Text Input Module

Interactive REPL (Read-Eval-Print Loop) with rich prompt,
command history, and auto-completion.

Usage:
    from modules.speech.text_input import TextInput
    text_input = TextInput(history_file="logs/.jarvis_history")
    user_text = await text_input.get_input()
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from loguru import logger
from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style


# ── Prompt Styling ────────────────────────────────────────

PROMPT_STYLE = Style.from_dict({
    "prompt_bracket": "#888888",
    "prompt_name": "#00d4ff bold",
    "prompt_arrow": "#ff6ec7 bold",
})

PROMPT_MESSAGE = [
    ("class:prompt_bracket", "["),
    ("class:prompt_name", "JARVIS"),
    ("class:prompt_bracket", "]"),
    ("class:prompt_arrow", " ❯ "),
]


# ── Built-in Commands ─────────────────────────────────────

BUILTIN_COMMANDS = {
    "exit":     "Shut down JARVIS",
    "quit":     "Shut down JARVIS",
    "help":     "Show available commands",
    "status":   "Show JARVIS system status",
    "history":  "Show command history",
    "clear":    "Clear the screen",
    "tools":    "List registered tools",
    "version":  "Show JARVIS version",
}


class TextInput:
    """
    Interactive text input handler with rich prompt.

    Features:
    - Colored prompt with JARVIS branding
    - Command history with file persistence
    - Auto-suggestions from history
    - Built-in command recognition
    - Multi-line input support (Shift+Enter)
    """

    def __init__(
        self,
        history_file: Optional[str] = None,
        max_history: int = 1000,
    ) -> None:
        # Ensure history directory exists
        if history_file:
            Path(history_file).parent.mkdir(parents=True, exist_ok=True)

        self._session = PromptSession(
            message=PROMPT_MESSAGE,
            style=PROMPT_STYLE,
            history=FileHistory(history_file) if history_file else None,
            auto_suggest=AutoSuggestFromHistory(),
            enable_history_search=True,
            multiline=False,
        )
        self._max_history = max_history
        logger.debug("TextInput initialized")

    async def get_input(self) -> Optional[str]:
        """
        Get user input from the terminal.

        Returns:
            The user's input string, or None if input was cancelled.
        """
        try:
            # Run prompt_toolkit in a thread to not block the event loop
            text = await asyncio.get_event_loop().run_in_executor(
                None, self._session.prompt
            )
            text = text.strip()
            if text:
                logger.debug(f"User input: '{text[:80]}...'")
            return text

        except (EOFError, KeyboardInterrupt):
            return None

    def is_builtin(self, text: str) -> bool:
        """Check if text is a built-in command."""
        return text.lower().split()[0] in BUILTIN_COMMANDS

    def is_exit(self, text: str) -> bool:
        """Check if text is an exit command."""
        return text.lower().strip() in ("exit", "quit", "bye", "shutdown")

    @staticmethod
    def builtin_help() -> str:
        """Generate help text for built-in commands."""
        lines = ["\n  📋 Built-in Commands:\n"]
        for cmd, desc in BUILTIN_COMMANDS.items():
            lines.append(f"    {cmd:<12} — {desc}")
        lines.append("")
        lines.append("  💡 Or just talk naturally:")
        lines.append('    "Open Firefox"')
        lines.append('    "Organize my downloads folder"')
        lines.append('    "What processes are running?"')
        lines.append("")
        return "\n".join(lines)
