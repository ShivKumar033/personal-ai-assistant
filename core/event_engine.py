"""
JARVIS AI — Event Engine (Skeleton)

Event-driven automation system using pub/sub pattern.
Full implementation comes in Phase 6.

Usage:
    from core.event_engine import EventEngine
    engine = EventEngine()
    engine.on("download_complete", organize_files)
    engine.emit("download_complete", {"path": "/downloads/file.zip"})
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Callable, Coroutine

from loguru import logger


# Type alias for event handlers
EventHandler = Callable[..., Coroutine[Any, Any, None]]


class EventEngine:
    """
    Simple async event bus for JARVIS.

    Supports:
    - Registering event handlers
    - Emitting events (async)
    - One-shot handlers
    - Event history
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[dict]] = defaultdict(list)
        self._event_history: list[dict] = []
        logger.debug("EventEngine initialized")

    def on(
        self, event: str, handler: EventHandler, once: bool = False
    ) -> None:
        """
        Register a handler for an event.

        Args:
            event: Event name (e.g., 'download_complete')
            handler: Async callable to invoke
            once: If True, handler is removed after first invocation
        """
        self._handlers[event].append({
            "handler": handler,
            "once": once,
        })
        logger.debug(
            f"Handler registered: '{event}' → {handler.__name__}"
            f"{' (once)' if once else ''}"
        )

    def off(self, event: str, handler: EventHandler) -> None:
        """Remove a handler for an event."""
        self._handlers[event] = [
            h for h in self._handlers[event]
            if h["handler"] != handler
        ]

    async def emit(self, event: str, data: Any = None) -> None:
        """
        Emit an event, calling all registered handlers.

        Args:
            event: Event name
            data: Event payload (any type)
        """
        handlers = self._handlers.get(event, [])
        if not handlers:
            logger.debug(f"Event '{event}' emitted — no handlers")
            return

        logger.info(f"Event '{event}' emitted — {len(handlers)} handler(s)")
        self._event_history.append({
            "event": event,
            "handlers": len(handlers),
        })

        to_remove = []
        for entry in handlers:
            try:
                await entry["handler"](data)
                if entry["once"]:
                    to_remove.append(entry)
            except Exception as e:
                logger.error(
                    f"Handler error for '{event}': {e}"
                )

        # Remove one-shot handlers
        for entry in to_remove:
            self._handlers[event].remove(entry)

    def list_events(self) -> list[str]:
        """List all events with registered handlers."""
        return list(self._handlers.keys())

    @property
    def event_history(self) -> list[dict]:
        return list(self._event_history)

    def clear(self) -> None:
        """Clear all handlers and history."""
        self._handlers.clear()
        self._event_history.clear()
        logger.debug("EventEngine cleared")
