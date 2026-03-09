"""
JARVIS AI — Tool Executor

Runs tools selected by the AI Brain, with security checks,
error handling, timeout management, and result reporting.

Usage:
    from tools.tool_executor import ToolExecutor
    executor = ToolExecutor(registry, permission_engine)
    result = await executor.execute("open_app", {"app_name": "firefox"})
"""

from __future__ import annotations

import asyncio
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from loguru import logger


class ExecutionStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    DENIED = "denied"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class ToolResult:
    """Result of a tool execution."""
    tool_name: str
    status: ExecutionStatus
    output: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def success(self) -> bool:
        return self.status == ExecutionStatus.SUCCESS

    def __str__(self) -> str:
        if self.success:
            return f"✅ {self.tool_name}: {self.output}"
        return f"❌ {self.tool_name}: {self.error or self.status.value}"


class ToolExecutor:
    """
    Executes tools from the ToolRegistry with security and error handling.

    Pipeline:
    1. Validate tool exists and is enabled
    2. Security check via PermissionEngine
    3. Request confirmation if needed
    4. Execute with timeout
    5. Log result
    6. Return formatted ToolResult
    """

    def __init__(
        self,
        registry,
        permission_engine,
        default_timeout: float = 30.0,
    ) -> None:
        self._registry = registry
        self._permission = permission_engine
        self._default_timeout = default_timeout
        self._execution_log: list[ToolResult] = []

        logger.debug("ToolExecutor initialized")

    async def execute(
        self,
        tool_name: str,
        params: Optional[dict[str, Any]] = None,
        timeout: Optional[float] = None,
        skip_confirmation: bool = False,
    ) -> ToolResult:
        """
        Execute a registered tool.

        Args:
            tool_name: Name of the tool to execute
            params: Tool parameters as key-value pairs
            timeout: Execution timeout in seconds
            skip_confirmation: Skip user confirmation for this call

        Returns:
            ToolResult with status and output
        """
        params = params or {}
        timeout = timeout or self._default_timeout
        start_time = time.monotonic()

        # ── Step 1: Validate tool ─────────────────────
        tool_def = self._registry.get(tool_name)
        if not tool_def:
            return self._log_result(ToolResult(
                tool_name=tool_name,
                status=ExecutionStatus.FAILED,
                error=f"Tool '{tool_name}' not found in registry",
            ))

        if not tool_def.enabled:
            return self._log_result(ToolResult(
                tool_name=tool_name,
                status=ExecutionStatus.FAILED,
                error=f"Tool '{tool_name}' is disabled",
            ))

        # ── Step 2: Security check ────────────────────
        perm_result = await self._permission.check_tool(
            tool_name, tool_def.category
        )

        if not perm_result.allowed:
            logger.warning(
                f"Tool '{tool_name}' DENIED: {perm_result.reason}"
            )
            return self._log_result(ToolResult(
                tool_name=tool_name,
                status=ExecutionStatus.DENIED,
                error=perm_result.reason,
            ))

        # ── Step 3: Confirmation if needed ────────────
        if perm_result.requires_confirmation and not skip_confirmation:
            approved = await self._permission.request_confirmation(
                f"Execute tool '{tool_name}' with params: {params}"
            )
            if not approved:
                return self._log_result(ToolResult(
                    tool_name=tool_name,
                    status=ExecutionStatus.CANCELLED,
                    error="User denied confirmation",
                ))

        # ── Step 4: Execute with timeout ──────────────
        try:
            logger.info(
                f"Executing tool: '{tool_name}' with params: {params}"
            )

            # Handle both sync and async tool handlers
            handler = tool_def.handler
            if asyncio.iscoroutinefunction(handler):
                output = await asyncio.wait_for(
                    handler(**params), timeout=timeout
                )
            else:
                # Run sync function in executor to not block event loop
                loop = asyncio.get_event_loop()
                output = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: handler(**params)),
                    timeout=timeout,
                )

            elapsed = (time.monotonic() - start_time) * 1000

            return self._log_result(ToolResult(
                tool_name=tool_name,
                status=ExecutionStatus.SUCCESS,
                output=output,
                execution_time_ms=round(elapsed, 2),
            ))

        except asyncio.TimeoutError:
            elapsed = (time.monotonic() - start_time) * 1000
            logger.error(
                f"Tool '{tool_name}' timed out after {timeout}s"
            )
            return self._log_result(ToolResult(
                tool_name=tool_name,
                status=ExecutionStatus.TIMEOUT,
                error=f"Execution timed out after {timeout}s",
                execution_time_ms=round(elapsed, 2),
            ))

        except Exception as e:
            elapsed = (time.monotonic() - start_time) * 1000
            tb = traceback.format_exc()
            logger.error(
                f"Tool '{tool_name}' failed: {e}\n{tb}"
            )
            return self._log_result(ToolResult(
                tool_name=tool_name,
                status=ExecutionStatus.FAILED,
                error=str(e),
                execution_time_ms=round(elapsed, 2),
            ))

    # ── Batch Execution ───────────────────────────────────

    async def execute_batch(
        self, tasks: list[dict], parallel: bool = False
    ) -> list[ToolResult]:
        """
        Execute multiple tools.

        Args:
            tasks: List of {"tool": "name", "params": {...}}
            parallel: If True, execute all tasks concurrently

        Returns:
            List of ToolResults
        """
        if parallel:
            coros = [
                self.execute(t["tool"], t.get("params", {}))
                for t in tasks
            ]
            return await asyncio.gather(*coros)
        else:
            results = []
            for task in tasks:
                result = await self.execute(
                    task["tool"], task.get("params", {})
                )
                results.append(result)
            return results

    # ── History ───────────────────────────────────────────

    @property
    def execution_log(self) -> list[ToolResult]:
        return list(self._execution_log)

    @property
    def last_result(self) -> Optional[ToolResult]:
        return self._execution_log[-1] if self._execution_log else None

    def _log_result(self, result: ToolResult) -> ToolResult:
        """Append to execution log and return."""
        self._execution_log.append(result)
        # Keep last 200 entries
        if len(self._execution_log) > 200:
            self._execution_log = self._execution_log[-200:]
        return result

    def summary(self) -> dict:
        """Executor summary."""
        total = len(self._execution_log)
        success = sum(1 for r in self._execution_log if r.success)
        return {
            "total_executions": total,
            "successful": success,
            "failed": total - success,
            "success_rate": f"{(success / total * 100):.1f}%" if total else "N/A",
        }
