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
from core.command_interpreter import CommandInterpreter
from security import PermissionEngine
from tools.tool_registry import ToolRegistry
from tools.tool_executor import ToolExecutor
from tools.builtin_tools import register_builtin_tools
from modules.speech.text_input import TextInput
from ai.brain import AIBrain
from ai.model_router import ModelRouter
from ai.planner import AgentPlanner
from ai.agent_executor import WorkflowRunner
from core.task_orchestrator import TaskOrchestrator


# ── Rich Console ──────────────────────────────────────────
console = Console()


class Assistant:
    """
    Main JARVIS controller.

    Orchestrates:
    - Natural language understanding via AI Brain
    - Command interpretation (keyword + AI)
    - Tool execution
    - Conversational responses
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

        # ── AI subsystems ─────────────────────────────
        self._model_router = ModelRouter(settings.ai)
        self._brain = AIBrain(settings.ai, self._model_router)
        self._interpreter = CommandInterpreter(
            brain=self._brain,
            registry=self._registry,
        )
        self._planner = AgentPlanner(self._brain, self._registry)
        self._workflow_runner = WorkflowRunner(self._brain, self._executor, self._state, self._planner)
        self._orchestrator = TaskOrchestrator(self._workflow_runner)

        # Register built-in tools
        register_builtin_tools(self._registry)

        logger.info("Assistant subsystems initialized")

    # ── Lifecycle ─────────────────────────────────────────

    async def start(self) -> None:
        """Start the JARVIS assistant main loop."""
        self._running = True
        self._state.status = JarvisStatus.IDLE

        # ── Initialize AI Brain ───────────────────────
        console.print(
            "\n[dim]  ⏳ Initializing AI Brain...[/dim]", end=""
        )
        await self._brain.initialize()

        # Update model router with backend availability
        backend_status = {
            name: backend.is_available
            for name, backend in self._brain._backends.items()
        }
        self._model_router.update_availability(backend_status)

        if self._brain.is_online:
            console.print(
                f"[green] ✓ Online[/green] "
                f"[dim]({self._brain.active_model})[/dim]"
            )
        else:
            console.print(
                "[yellow] ⚠ Offline mode[/yellow] "
                "[dim](start Ollama or set OpenAI key)[/dim]"
            )

        # Print boot banner
        self._print_banner()

        # Emit boot event
        await self._events.emit("jarvis_started")

        # Start Task Orchestrator
        await self._orchestrator.start()

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

        # Close subsystems
        await self._orchestrator.stop()
        await self._brain.close()

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

        Pipeline:
        1. Check for built-in commands (help, status, etc.)
        2. Run through CommandInterpreter (direct → keyword → AI)
        3. Execute tool if one was matched
        4. Return conversational response if no tool
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
        elif command == "brain":
            return self._handle_brain_status()
        elif command.startswith("plan "):
            task = user_input[5:].strip()
            task_id = self._orchestrator.enqueue(task)
            return f"✅ Queued autonomous workflow: '{task}' (ID: {task_id})"

        # ── Interpret the command ─────────────────────
        intent = await self._interpreter.interpret(user_input)

        logger.info(
            f"Intent: {intent.intent} | tool={intent.tool_name} | "
            f"confidence={intent.confidence:.2f} | source={intent.source}"
        )

        # ── Execute tool if matched ───────────────────
        if intent.tool_name and not intent.is_conversational:
            self._state.status = JarvisStatus.EXECUTING

            result = await self._executor.execute(
                intent.tool_name,
                intent.tool_params,
            )

            # Build response
            if result.success:
                response_text = self._format_tool_output(
                    intent.tool_name, result.output
                )
                # If AI provided a response, prefix it
                if intent.response_text and intent.source == "ai":
                    response_text = (
                        f"  {intent.response_text}\n\n{response_text}"
                    )
            else:
                response_text = f"❌ {result.error}"
                if intent.response_text:
                    response_text = (
                        f"  {intent.response_text}\n\n  {response_text}"
                    )

            # Log to context & state
            self._context.add_exchange(
                user_input,
                str(result.output) if result.success else str(result.error),
                intent=intent.intent,
                entities=intent.entities,
                success=result.success,
            )
            self._state.log_command(
                user_input, str(result), result.success
            )
            self._state.status = JarvisStatus.IDLE
            return response_text

        # ── Conversational response ───────────────────
        if intent.response_text:
            # AI already generated a response
            self._context.add_exchange(
                user_input,
                intent.response_text,
                intent=intent.intent,
                entities=intent.entities,
                success=True,
            )
            self._state.log_command(user_input, "responded", True)
            self._state.status = JarvisStatus.IDLE

            model_tag = ""
            if intent.model_used:
                model_tag = f"\n\n  [dim]— {intent.model_used}[/dim]"
            return f"  {intent.response_text}{model_tag}"

        # ── AI Brain conversational fallback ──────────
        if self._brain.is_online:
            self._state.status = JarvisStatus.THINKING
            context_str = self._context.build_prompt_context(max_exchanges=5)
            response = await self._brain.respond(user_input, context=context_str)

            self._context.add_exchange(
                user_input, response,
                intent="conversation",
                success=True,
            )
            self._state.log_command(user_input, "ai_response", True)
            self._state.status = JarvisStatus.IDLE

            return (
                f"  {response}\n\n"
                f"  [dim]— {self._brain.active_model}[/dim]"
            )

        # ── Fully offline fallback ────────────────────
        self._context.add_exchange(
            user_input,
            "(offline)",
            intent="unknown",
            success=True,
        )
        self._state.log_command(user_input, "offline", True)
        self._state.status = JarvisStatus.IDLE

        return (
            f"🧠 I understood: \"{user_input}\"\n\n"
            f"   No AI model is connected. Start Ollama or configure OpenAI.\n"
            f"   I can still execute built-in tools — type [bold]tools[/bold] to see them."
        )

    # ── Built-in Command Handlers ─────────────────────────

    def _handle_help(self) -> str:
        """Return help text."""
        return self._text_input.builtin_help()

    def _handle_version(self) -> str:
        """Return version info."""
        s = self._settings.jarvis
        brain_status = "🟢 Online" if self._brain.is_online else "🔴 Offline"
        return (
            f"  🤖 {s.name} v{s.version} (codename: {s.codename})\n"
            f"  📦 Platform: {self._settings.resolve_platform()}\n"
            f"  🧠 AI Brain: {brain_status} ({self._brain.active_model})\n"
            f"  🔒 Security: {'Enabled' if self._settings.security.confirmation_required else 'Relaxed'}"
        )

    def _handle_status(self) -> str:
        """Return system status."""
        state = self._state.summary()
        res = state["resources"]
        sys_info = state["system"]
        brain = self._brain.status()

        brain_icon = "🟢" if brain["online"] else "🔴"
        backends_str = ""
        for name, info in brain.get("backends", {}).items():
            icon = "✅" if info["available"] else "❌"
            backends_str += f"\n               {icon} {name}: {info['model']}"

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
            f"  {'─' * 40}",
            f"  {brain_icon} AI Brain: {brain['active_model']}{backends_str}",
        ]
        return "\n".join(lines)

    def _handle_brain_status(self) -> str:
        """Return detailed AI Brain status."""
        brain = self._brain.status()

        lines = [
            f"  🧠 AI Brain Status",
            f"  {'─' * 40}",
            f"  Online:      {'Yes' if brain['online'] else 'No'}",
            f"  Active:      {brain['active_model']}",
            f"  Initialized: {'Yes' if brain['initialized'] else 'No'}",
            f"  ",
            f"  Backends:",
        ]

        for name, info in brain.get("backends", {}).items():
            icon = "✅" if info["available"] else "❌"
            lines.append(f"    {icon} {name}: {info['model']}")

        lines.extend([
            f"  ",
            f"  Routing Rules:",
        ])
        for rule in self._model_router.get_rules():
            lines.append(
                f"    {rule['task_type']:<20} → {rule['preferred']} "
                f"(fallback: {rule['fallback']})"
            )

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

        lines.append("  Usage: type the tool name, or describe what you want naturally.")
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
        brain_status = (
            f"[green]Online[/green] ({self._brain.active_model})"
            if self._brain.is_online
            else "[yellow]Offline[/yellow]"
        )

        info_lines = (
            f"[bold cyan]{s.name}[/bold cyan] v{s.version} "
            f"[dim](codename: {s.codename})[/dim]\n"
            f"[dim]Platform: {sys_info.os_name} {sys_info.os_version} | "
            f"Python {sys_info.python_version} | "
            f"{sys_info.cpu_count} cores | "
            f"{sys_info.total_memory_gb} GB RAM[/dim]\n\n"
            f"[bright_cyan]🧠 AI Brain:[/bright_cyan] {brain_status} | "
            f"[bright_cyan]🔒 Security:[/bright_cyan] "
            f"{'Active' if self._settings.security.confirmation_required else 'Relaxed'} | "
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
