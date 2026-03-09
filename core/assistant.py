"""
JARVIS AI — Main Assistant Controller

The central coordinator that ties all JARVIS subsystems together.
Handles the main command loop, routes commands to appropriate handlers,
and manages the lifecycle of the assistant.

Usage:
    from core.assistant import Assistant
    assistant = Assistant(settings)
    await assistant.start()
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Optional

from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from config import Settings, PROJECT_ROOT
from core.context_manager import ContextManager
from core.state_manager import StateManager, JarvisStatus
from core.event_engine import EventEngine
from security import PermissionEngine
from tools.tool_registry import ToolRegistry
from tools.tool_executor import ToolExecutor
from tools.builtin_tools import register_builtin_tools
from modules.speech.text_input import TextInput


# ── Rich Console ──────────────────────────────────────────
console = Console()


class Assistant:
    """
    Main JARVIS controller.

    Orchestrates:
    - Text input processing
    - Built-in command handling
    - Tool execution
    - State & context management
    - Event emission
    - Security enforcement
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._running = False

        # ── Initialize subsystems ─────────────────────
        self._state = StateManager()
        self._context = ContextManager(max_history=50)
        self._events = EventEngine()
        self._permission = PermissionEngine(settings.security)
        self._registry = ToolRegistry()
        self._executor = ToolExecutor(
            self._registry,
            self._permission,
            default_timeout=settings.resources.task_timeout_seconds,
        )
        self._text_input = TextInput(
            history_file=str(settings.history_path),
        )

        # Register built-in tools
        register_builtin_tools(self._registry)

        logger.info("Assistant subsystems initialized")

    # ── Lifecycle ─────────────────────────────────────────

    async def start(self) -> None:
        """Start the JARVIS assistant main loop."""
        self._running = True
        self._state.status = JarvisStatus.IDLE

        # Print boot banner
        self._print_banner()

        # Emit boot event
        await self._events.emit("jarvis_started")

        # Main REPL loop
        while self._running:
            try:
                self._state.status = JarvisStatus.LISTENING

                # Get user input
                user_input = await self._text_input.get_input()

                if user_input is None:
                    continue

                # Check for exit
                if self._text_input.is_exit(user_input):
                    await self.shutdown()
                    break

                # Process the command
                self._state.status = JarvisStatus.THINKING
                response = await self.process(user_input)

                # Display response
                if response:
                    self._display_response(response)

            except KeyboardInterrupt:
                console.print("\n[dim]Interrupt received...[/dim]")
                await self.shutdown()
                break
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
                self._state.status = JarvisStatus.ERROR
                console.print(
                    f"[red]❌ Error: {e}[/red]\n"
                    "[dim]JARVIS is recovering...[/dim]"
                )
                self._state.status = JarvisStatus.IDLE

    async def shutdown(self) -> None:
        """Gracefully shut down JARVIS."""
        self._running = False
        self._state.status = JarvisStatus.SHUTTING_DOWN

        console.print()
        console.print(
            Panel(
                "[bold cyan]Shutting down JARVIS...[/bold cyan]\n"
                "[dim]All systems going offline. Goodbye, sir.[/dim]",
                border_style="cyan",
                box=box.ROUNDED,
            )
        )

        await self._events.emit("jarvis_shutdown")
        logger.info("JARVIS shut down gracefully")

    # ── Command Processing ────────────────────────────────

    async def process(self, user_input: str) -> Optional[str]:
        """
        Process a user command and return a response.

        Routes to:
        1. Built-in commands (help, status, tools, etc.)
        2. Tool execution (if a matching tool is found)
        3. Echo-back (Phase 1 — no AI brain yet)
        """
        command = user_input.strip().lower()

        # ── Built-in commands ─────────────────────────
        if command == "help":
            return self._handle_help()
        elif command == "status":
            return self._handle_status()
        elif command == "tools":
            return self._handle_tools()
        elif command == "history":
            return self._handle_history()
        elif command == "clear":
            os.system("clear" if self._settings.is_linux else "cls")
            return None
        elif command == "version":
            return self._handle_version()

        # ── Direct tool invocation ────────────────────
        # Try to match "tool_name" or "tool_name arg1 arg2"
        parts = user_input.strip().split(maxsplit=1)
        tool_name = parts[0].lower().replace("-", "_")

        if self._registry.exists(tool_name):
            self._state.status = JarvisStatus.EXECUTING

            # Parse simple args (Phase 1 — basic parsing)
            params = {}
            if len(parts) > 1:
                # Try JSON first
                try:
                    params = json.loads(parts[1])
                except (json.JSONDecodeError, ValueError):
                    # Fall back to first arg as filter/query
                    tool_def = self._registry.get(tool_name)
                    if tool_def and tool_def.parameters:
                        first_param = list(tool_def.parameters.keys())[0]
                        params = {first_param: parts[1]}

            result = await self._executor.execute(tool_name, params)

            # Log to context & state
            self._context.add_exchange(
                user_input,
                str(result.output) if result.success else str(result.error),
                intent=tool_name,
                success=result.success,
            )
            self._state.log_command(
                user_input,
                str(result),
                result.success,
            )
            self._state.status = JarvisStatus.IDLE

            if result.success:
                return self._format_tool_output(tool_name, result.output)
            else:
                return f"❌ {result.error}"

        # ── No AI brain yet (Phase 1) ────────────────
        # In Phase 2, this will route to the AI Brain
        self._context.add_exchange(
            user_input,
            "(AI Brain not yet connected — coming in Phase 2)",
            intent="unknown",
            success=True,
        )
        self._state.log_command(user_input, "echoed", True)
        self._state.status = JarvisStatus.IDLE

        return (
            f"🧠 I understood: \"{user_input}\"\n"
            f"\n"
            f"   [Phase 1] AI Brain is not yet connected.\n"
            f"   I can execute built-in tools — type [bold]tools[/bold] to see them,\n"
            f"   or type [bold]help[/bold] for all commands.\n"
            f"\n"
            f"   💡 AI understanding arrives in Phase 2!"
        )

    # ── Built-in Command Handlers ─────────────────────────

    def _handle_help(self) -> str:
        """Return help text."""
        return self._text_input.builtin_help()

    def _handle_version(self) -> str:
        """Return version info."""
        s = self._settings.jarvis
        return (
            f"  🤖 {s.name} v{s.version} (codename: {s.codename})\n"
            f"  📦 Platform: {self._settings.resolve_platform()}\n"
            f"  🧠 AI Model: {self._settings.ai.default_model}\n"
            f"  🔒 Security: {'Enabled' if self._settings.security.confirmation_required else 'Relaxed'}"
        )

    def _handle_status(self) -> str:
        """Return system status."""
        state = self._state.summary()
        res = state["resources"]
        sys_info = state["system"]

        lines = [
            f"  📊 JARVIS Status Dashboard",
            f"  {'─' * 40}",
            f"  Status:      {state['status']}",
            f"  Uptime:      {state['uptime_seconds']:.0f}s",
            f"  OS:          {sys_info['os']} ({sys_info['hostname']})",
            f"  CPU:         {res['cpu_percent']:.1f}%  ({sys_info['cpu_count']} cores)",
            f"  Memory:      {res['memory_percent']:.1f}%  ({sys_info['memory_gb']} GB total)",
            f"  Active Tasks:{state['active_tasks']}",
            f"  Commands Run:{state['total_commands']}",
            f"  Tools:       {self._registry.count} registered",
        ]
        return "\n".join(lines)

    def _handle_tools(self) -> str:
        """Return list of registered tools."""
        tools = self._registry.list_tools()
        if not tools:
            return "  No tools registered."

        lines = [f"  🧰 Registered Tools ({len(tools)}):", ""]

        # Group by category
        categories: dict[str, list] = {}
        for t in tools:
            categories.setdefault(t.category, []).append(t)

        for cat, cat_tools in sorted(categories.items()):
            lines.append(f"  [{cat.upper()}]")
            for t in cat_tools:
                risk_icon = {"safe": "🟢", "confirm": "🟡", "blocked": "🔴"}.get(
                    t.risk_level, "⚪"
                )
                lines.append(f"    {risk_icon} {t.name:<20} — {t.description}")
            lines.append("")

        lines.append("  Usage: type the tool name directly (e.g., 'system_info')")
        return "\n".join(lines)

    def _handle_history(self) -> str:
        """Return recent command history."""
        history = self._state.command_history
        if not history:
            return "  No commands in history yet."

        lines = ["  📜 Recent Commands:", ""]
        for entry in history[-10:]:
            icon = "✅" if entry["success"] else "❌"
            ts = entry["timestamp"][:19]
            lines.append(
                f"    {icon} [{ts}] {entry['command'][:60]}"
            )
        return "\n".join(lines)

    # ── Output Formatting ─────────────────────────────────

    def _format_tool_output(self, tool_name: str, output) -> str:
        """Format tool output for display."""
        if isinstance(output, dict):
            return f"  ✅ {tool_name}:\n" + self._dict_to_str(output, indent=4)
        elif isinstance(output, list):
            if not output:
                return f"  ✅ {tool_name}: (empty result)"
            if isinstance(output[0], dict):
                # Format as table-like output
                lines = [f"  ✅ {tool_name} ({len(output)} results):"]
                for i, item in enumerate(output[:15], 1):
                    lines.append(f"    {i}. {self._dict_to_str_compact(item)}")
                if len(output) > 15:
                    lines.append(f"    ... and {len(output) - 15} more")
                return "\n".join(lines)
            return f"  ✅ {tool_name}: {output}"
        elif isinstance(output, str):
            return f"  ✅ {tool_name}:\n  {output}"
        return f"  ✅ {tool_name}: {output}"

    def _dict_to_str(self, d: dict, indent: int = 2) -> str:
        """Pretty-print a dict."""
        lines = []
        pad = " " * indent
        for key, value in d.items():
            if isinstance(value, dict):
                lines.append(f"{pad}{key}:")
                lines.append(self._dict_to_str(value, indent + 2))
            else:
                lines.append(f"{pad}{key}: {value}")
        return "\n".join(lines)

    def _dict_to_str_compact(self, d: dict) -> str:
        """Compact one-line dict representation."""
        parts = [f"{k}={v}" for k, v in d.items()]
        return " | ".join(parts)

    def _display_response(self, response: str) -> None:
        """Display a JARVIS response with rich formatting."""
        console.print()
        console.print(
            Panel(
                response,
                title="[bold bright_cyan]JARVIS[/bold bright_cyan]",
                border_style="bright_cyan",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )

    # ── Boot Banner ───────────────────────────────────────

    def _print_banner(self) -> None:
        """Print the JARVIS boot banner."""
        banner_text = r"""
     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
     ██║███████║██████╔╝██║   ██║██║███████╗
██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
        """

        s = self._settings.jarvis
        sys_info = self._state.system_info

        info_lines = (
            f"[bold cyan]{s.name}[/bold cyan] v{s.version} "
            f"[dim](codename: {s.codename})[/dim]\n"
            f"[dim]Platform: {sys_info.os_name} {sys_info.os_version} | "
            f"Python {sys_info.python_version} | "
            f"{sys_info.cpu_count} cores | "
            f"{sys_info.total_memory_gb} GB RAM[/dim]\n\n"
            f"[bright_cyan]🔒 Security:[/bright_cyan] "
            f"{'Active' if s else 'Relaxed'} | "
            f"[bright_cyan]🧰 Tools:[/bright_cyan] "
            f"{self._registry.count} loaded\n\n"
            f"[dim]Type [bold]help[/bold] for commands, "
            f"or just talk to me naturally.[/dim]"
        )

        console.print()
        console.print(
            Panel(
                f"[bright_cyan]{banner_text}[/bright_cyan]\n{info_lines}",
                border_style="bright_cyan",
                box=box.DOUBLE_EDGE,
                padding=(0, 2),
            )
        )
        console.print()
