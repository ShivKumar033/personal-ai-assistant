"""
JARVIS AI — State Manager

Manages global application state including system info, active tasks,
and runtime status. Thread-safe singleton.

Usage:
    from core.state_manager import StateManager
    state = StateManager()
    state.set("active_task", "pentesting_setup")
"""

from __future__ import annotations

import asyncio
import platform
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import psutil
from loguru import logger


class JarvisStatus(str, Enum):
    """JARVIS operational states."""
    BOOTING = "booting"
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    EXECUTING = "executing"
    ERROR = "error"
    SHUTTING_DOWN = "shutting_down"


@dataclass
class SystemInfo:
    """Snapshot of system information."""
    os_name: str
    os_version: str
    hostname: str
    cpu_count: int
    total_memory_gb: float
    python_version: str

    @classmethod
    def capture(cls) -> "SystemInfo":
        """Capture current system info."""
        mem = psutil.virtual_memory()
        return cls(
            os_name=platform.system(),
            os_version=platform.release(),
            hostname=platform.node(),
            cpu_count=psutil.cpu_count(logical=True),
            total_memory_gb=round(mem.total / (1024 ** 3), 2),
            python_version=platform.python_version(),
        )


@dataclass
class ResourceSnapshot:
    """Point-in-time resource usage."""
    cpu_percent: float
    memory_percent: float
    memory_used_gb: float
    disk_percent: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def capture(cls) -> "ResourceSnapshot":
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return cls(
            cpu_percent=psutil.cpu_percent(interval=0.1),
            memory_percent=mem.percent,
            memory_used_gb=round(mem.used / (1024 ** 3), 2),
            disk_percent=disk.percent,
        )


class StateManager:
    """
    Thread-safe global state manager for JARVIS.

    Stores:
    - JARVIS operational status
    - System information
    - Active tasks & agents
    - Custom key-value state
    - Session metadata
    """

    _instance: Optional["StateManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "StateManager":
        """Singleton pattern — only one StateManager exists."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        self._status: JarvisStatus = JarvisStatus.BOOTING
        self._state: dict[str, Any] = {}
        self._active_tasks: dict[str, dict] = {}
        self._command_history: list[dict] = []
        self._boot_time: datetime = datetime.now(timezone.utc)
        self._system_info: SystemInfo = SystemInfo.capture()
        self._state_lock = threading.Lock()

        logger.debug("StateManager initialized")

    # ── Status ────────────────────────────────────────────

    @property
    def status(self) -> JarvisStatus:
        return self._status

    @status.setter
    def status(self, value: JarvisStatus) -> None:
        old = self._status
        self._status = value
        if old != value:
            logger.info(f"Status changed: {old.value} → {value.value}")

    @property
    def uptime_seconds(self) -> float:
        return (datetime.now(timezone.utc) - self._boot_time).total_seconds()

    @property
    def system_info(self) -> SystemInfo:
        return self._system_info

    # ── Key-Value State ───────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """Get a state value by key."""
        with self._state_lock:
            return self._state.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a state value."""
        with self._state_lock:
            self._state[key] = value
            logger.debug(f"State[{key}] = {value!r}")

    def delete(self, key: str) -> None:
        """Delete a state key."""
        with self._state_lock:
            self._state.pop(key, None)

    def all_state(self) -> dict[str, Any]:
        """Return a copy of all state."""
        with self._state_lock:
            return dict(self._state)

    # ── Task Tracking ─────────────────────────────────────

    def register_task(self, task_id: str, description: str) -> None:
        """Register an active task."""
        self._active_tasks[task_id] = {
            "description": description,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": "running",
        }
        logger.info(f"Task registered: [{task_id}] {description}")

    def complete_task(self, task_id: str, result: str = "success") -> None:
        """Mark a task as complete."""
        if task_id in self._active_tasks:
            self._active_tasks[task_id]["status"] = "completed"
            self._active_tasks[task_id]["result"] = result
            logger.info(f"Task completed: [{task_id}] → {result}")

    def fail_task(self, task_id: str, error: str) -> None:
        """Mark a task as failed."""
        if task_id in self._active_tasks:
            self._active_tasks[task_id]["status"] = "failed"
            self._active_tasks[task_id]["error"] = error
            logger.error(f"Task failed: [{task_id}] → {error}")

    @property
    def active_tasks(self) -> dict[str, dict]:
        return {
            k: v for k, v in self._active_tasks.items()
            if v["status"] == "running"
        }

    # ── Command History ───────────────────────────────────

    def log_command(self, command: str, result: str, success: bool) -> None:
        """Log a command to history."""
        entry = {
            "command": command,
            "result": result,
            "success": success,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._command_history.append(entry)
        # Keep last 500 entries in memory
        if len(self._command_history) > 500:
            self._command_history = self._command_history[-500:]

    @property
    def command_history(self) -> list[dict]:
        return list(self._command_history)

    @property
    def last_command(self) -> Optional[dict]:
        return self._command_history[-1] if self._command_history else None

    # ── Resource Check ────────────────────────────────────

    def get_resources(self) -> ResourceSnapshot:
        """Get current resource usage."""
        return ResourceSnapshot.capture()

    def is_resource_constrained(
        self, max_cpu: int = 80, max_mem: int = 85
    ) -> bool:
        """Check if system resources are constrained."""
        snap = self.get_resources()
        return snap.cpu_percent > max_cpu or snap.memory_percent > max_mem

    # ── Summary ───────────────────────────────────────────

    def summary(self) -> dict:
        """Full state summary for display / API."""
        resources = self.get_resources()
        return {
            "status": self._status.value,
            "uptime_seconds": round(self.uptime_seconds, 1),
            "system": {
                "os": self._system_info.os_name,
                "hostname": self._system_info.hostname,
                "cpu_count": self._system_info.cpu_count,
                "memory_gb": self._system_info.total_memory_gb,
            },
            "resources": {
                "cpu_percent": resources.cpu_percent,
                "memory_percent": resources.memory_percent,
            },
            "active_tasks": len(self.active_tasks),
            "total_commands": len(self._command_history),
        }

    def reset(self) -> None:
        """Reset state (for testing)."""
        with self._state_lock:
            self._state.clear()
            self._active_tasks.clear()
            self._command_history.clear()
            self._status = JarvisStatus.BOOTING
