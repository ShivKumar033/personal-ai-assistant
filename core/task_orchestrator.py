"""
JARVIS AI — Task Orchestrator (Phase 4)

Manages task queues, scheduling, background task monitoring,
and parallel execution.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid
from typing import Any, Callable, Dict, List, Optional
import croniter

from loguru import logger

from tools.tool_executor import ToolExecutor



@dataclass
class ScheduledTask:
    """A task scheduled using a cron expression."""
    name: str
    cron_expr: str
    action: Callable
    kwargs: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    last_run: Optional[datetime] = None
    
    def get_next_run(self) -> datetime:
        """Calculate the next run time."""
        now = datetime.now(timezone.utc)
        iterator = croniter.croniter(self.cron_expr, now)
        return iterator.get_next(datetime)


@dataclass
class QueuedTask:
    """A task waiting in the execution queue."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    priority: int = 1  # 1 is highest
    status: str = "pending" # pending, running, completed, failed
    result: Any = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class TaskOrchestrator:
    """
    Manages JARVIS's task queues and background scheduling.
    Allows for parallel execution and cron-like jobs.
    """
    
    def __init__(self, workflow_runner) -> None:
        self.runner = workflow_runner
        self._queue: List[QueuedTask] = []
        self._schedules: Dict[str, ScheduledTask] = {}
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._is_running: bool = False
        self._loop_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the orchestrator background loops."""
        if self._is_running:
            return
            
        self._is_running = True
        self._loop_task = asyncio.create_task(self._orchestration_loop())
        logger.info("Task Orchestrator started.")

    async def stop(self) -> None:
        """Stop the orchestrator and all active tasks."""
        self._is_running = False
        if self._loop_task:
            self._loop_task.cancel()
            
        # Cancel all active tasks
        for task_id, task in self._active_tasks.items():
            if not task.done():
                task.cancel()
                logger.info(f"Cancelled active task: {task_id}")
                
        self._active_tasks.clear()
        logger.info("Task Orchestrator stopped.")

    def enqueue(self, task_description: str, priority: int = 2) -> str:
        """Add a complex workflow task to the execution queue."""
        qt = QueuedTask(description=task_description, priority=priority)
        self._queue.append(qt)
        # Sort queue by priority (1 is highest)
        self._queue.sort(key=lambda t: t.priority)
        logger.info(f"Queued task [{qt.id}]: '{qt.description}' (priority {priority})")
        return qt.id

    def schedule(self, name: str, cron_expr: str, action: Callable, **kwargs) -> None:
        """Schedule a recurring task.
        
        Example: orchestrator.schedule("morning_routine", "0 9 * * *", runner.run_workspace, workspace_type="development")
        """
        try:
            # Validate cron expression
            croniter.croniter(cron_expr, datetime.now())
            task = ScheduledTask(name=name, cron_expr=cron_expr, action=action, kwargs=kwargs)
            self._schedules[name] = task
            logger.info(f"Scheduled task '{name}' with pattern '{cron_expr}'. Next run: {task.get_next_run()}")
        except Exception as e:
            logger.error(f"Failed to schedule task '{name}': {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get the status of all queued, active, and scheduled tasks."""
        pending = [t for t in self._queue if t.status == "pending"]
        completed = [t for t in self._queue if t.status in ("completed", "failed")]
        
        schedules = [
            {
                "name": name, 
                "cron": task.cron_expr, 
                "enabled": task.enabled,
                "next_run": task.get_next_run().isoformat(),
                "last_run": task.last_run.isoformat() if task.last_run else None
            }
            for name, task in self._schedules.items()
        ]
        
        return {
            "is_running": self._is_running,
            "active_count": len(self._active_tasks),
            "pending_count": len(pending),
            "completed_count": len(completed),
            "schedules": schedules,
            "queue": [
                {
                    "id": t.id,
                    "description": t.description,
                    "status": t.status,
                    "priority": t.priority,
                } for t in self._queue
            ]
        }

    async def _orchestration_loop(self) -> None:
        """Background loop that checks for scheduled and queued tasks."""
        try:
            while self._is_running:
                now = datetime.now(timezone.utc)
                
                # 1. Check Scheduled Tasks
                for name, sched in self._schedules.items():
                    if not sched.enabled:
                        continue
                        
                    # Calculate if it's time to run
                    if sched.last_run:
                        # Simple naive check: if current time > next run time calculated from last_run
                        iterator = croniter.croniter(sched.cron_expr, sched.last_run)
                        next_run = iterator.get_next(datetime)
                    else:
                        iterator = croniter.croniter(sched.cron_expr, now)
                        # We pretend last run was "next run minus interval"
                        next_run = iterator.get_prev(datetime)
                        
                    if datetime.now(timezone.utc).replace(tzinfo=None) >= next_run.replace(tzinfo=None) if next_run.tzinfo else datetime.now(timezone.utc) >= next_run:
                        logger.info(f"Executing scheduled task: {name}")
                        sched.last_run = now
                        
                        # Run the action async
                        task = asyncio.create_task(sched.action(**sched.kwargs))
                        self._active_tasks[f"sched_{name}_{now.timestamp()}"] = task
                        
                # 2. Process Task Queue
                # Start pending tasks if we have capacity (max 3 concurrent)
                if len(self._active_tasks) < 3:
                    for qt in self._queue:
                        if qt.status == "pending":
                            qt.status = "running"
                            qt.started_at = now
                            logger.info(f"Starting queued task: {qt.id}")
                            
                            # Execute workflow in background task
                            task = asyncio.create_task(self._execute_queued_workflow(qt))
                            self._active_tasks[qt.id] = task
                            break # Start one per loop iteration
                
                # Clean up completed tasks from active dict
                done_tasks = [tid for tid, task in self._active_tasks.items() if task.done()]
                for tid in done_tasks:
                    try:
                        # Check for exceptions
                        exc = self._active_tasks[tid].exception()
                        if exc:
                            logger.error(f"Task {tid} failed with exception: {exc}")
                    except asyncio.CancelledError:
                        pass
                    del self._active_tasks[tid]

                await asyncio.sleep(5.0) # Check every 5 seconds
                
        except asyncio.CancelledError:
            logger.info("Orchestration loop cancelled.")
        except Exception as e:
            logger.error(f"Orchestration loop crashed: {e}")
            self._is_running = False

    async def _execute_queued_workflow(self, qt: QueuedTask) -> None:
        """Execute a single queued task using the WorkflowRunner."""
        try:
            result = await self.runner.run_task(qt.description)
            qt.status = "completed" if result.success else "failed"
            qt.result = result
            logger.info(f"Queued task {qt.id} finished with status '{qt.status}'")
        except Exception as e:
            qt.status = "failed"
            qt.result = str(e)
            logger.error(f"Queued task {qt.id} threw exception: {e}")
        finally:
            qt.completed_at = datetime.now(timezone.utc)
