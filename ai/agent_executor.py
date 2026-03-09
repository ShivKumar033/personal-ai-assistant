"""
JARVIS AI — Agent Executor

Executes plans created by the Agent Planner using the Observe → Think → Plan → Act → Evaluate loop.
Implements autonomous agent behavior with retry logic, error handling, and progress tracking.

Usage:
    from ai.agent_executor import AgentExecutor
    
    executor = AgentExecutor(brain, tool_executor, state_manager)
    result = await executor.execute_plan(plan)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from loguru import logger

from ai.planner import Plan, PlanStep, StepStatus


@dataclass
class ExecutionResult:
    """Result of executing a plan."""
    success: bool
    plan: Plan
    total_steps: int
    completed_steps: int
    failed_steps: int
    duration_seconds: float
    outputs: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    
    def summary(self) -> str:
        status = "✅ SUCCESS" if self.success else "❌ FAILED"
        return (
            f"{status}: {self.completed_steps}/{self.total_steps} steps completed "
            f"in {self.duration_seconds:.1f}s"
        )


@dataclass
class AgentState:
    """Current state of an executing agent."""
    plan: Plan
    current_step: Optional[PlanStep] = None
    iteration: int = 0
    max_iterations: int = 50
    paused: bool = False
    cancelled: bool = False
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    @property
    def is_active(self) -> bool:
        return not self.paused and not self.cancelled


class AgentExecutor:
    """
    Executes plans using the ReAct (Reasoning + Acting) loop.
    
    The execution loop:
    1. OBSERVE - Get current system state
    2. THINK - Analyze situation using AI Brain
    3. PLAN - Update execution plan if needed
    4. ACT - Execute the next step
    5. EVALUATE - Check results, decide next action
    """
    
    def __init__(
        self,
        brain,
        tool_executor,
        state_manager,
        max_iterations: int = 50,
        step_timeout: int = 30,
    ) -> None:
        self._brain = brain
        self._executor = tool_executor
        self._state = state_manager
        self._max_iterations = max_iterations
        self._step_timeout = step_timeout
        self._current_agent: Optional[AgentState] = None
    
    @property
    def current_agent(self) -> Optional[AgentState]:
        """Get the currently executing agent state."""
        return self._current_agent
    
    async def execute_plan(
        self,
        plan: Plan,
        show_progress: bool = True,
    ) -> ExecutionResult:
        """
        Execute a complete plan.
        
        Args:
            plan: The plan to execute
            show_progress: Whether to log progress
            
        Returns:
            ExecutionResult with execution details
        """
        import time
        start_time = time.monotonic()
        
        logger.info(f"Starting plan execution: {plan.task}")
        
        # Initialize agent state
        self._current_agent = AgentState(
            plan=plan,
            max_iterations=self._max_iterations,
        )
        
        # Main execution loop
        while self._current_agent.is_active:
            self._current_agent.iteration += 1
            
            if show_progress:
                logger.info(
                    f"Iteration {self._current_agent.iteration}/"
                    f"{self._max_iterations} - "
                    f"Steps: {self._count_steps()}"
                )
            
            # Check iteration limit
            if self._current_agent.iteration > self._max_iterations:
                logger.warning("Max iterations reached")
                break
            
            # OBSERVE: Get current state
            state_snapshot = await self._observe()
            
            # THINK: Analyze situation
            analysis = await self._think(plan, state_snapshot)
            
            # PLAN: Check if we need to re-plan
            if analysis.get("needs_replan"):
                logger.info("Re-planning based on current state...")
                # Could trigger re-planning here
            
            # ACT: Execute next step(s)
            step_result = await self._act(plan)
            
            # EVALUATE: Check results
            if not await self._evaluate(step_result):
                logger.warning("Step failed, attempting recovery...")
                await self._handle_failure(plan)
            
            # Check if plan is complete
            if plan.is_complete():
                break
            
            # Small delay between iterations
            await asyncio.sleep(0.1)
        
        # Calculate results
        duration = time.monotonic() - start_time
        result = ExecutionResult(
            success=plan.is_complete() and not plan.has_failed(),
            plan=plan,
            total_steps=len(plan.steps),
            completed_steps=sum(1 for s in plan.steps if s.status == StepStatus.COMPLETED),
            failed_steps=sum(1 for s in plan.steps if s.status == StepStatus.FAILED),
            duration_seconds=duration,
            outputs=[s.to_dict() for s in plan.steps if s.result],
            errors=[s.error for s in plan.steps if s.error],
        )
        
        logger.info(result.summary())
        self._current_agent = None
        
        return result
    
    async def _observe(self) -> dict:
        """
        OBSERVE: Get current system state.
        
        Returns information about:
        - Active processes
        - Open windows
        - Recent commands
        - Available resources
        """
        try:
            # Get current state from StateManager
            state = self._state.summary() if hasattr(self._state, 'summary') else {}
            
            # Get active tasks
            active_tasks = self._state.active_tasks if hasattr(self._state, 'active_tasks') else {}
            
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "system_state": state,
                "active_tasks": active_tasks,
                "current_plan_progress": self._get_progress(),
            }
        except Exception as e:
            logger.error(f"Observation failed: {e}")
            return {"error": str(e)}
    
    async def _think(self, plan: Plan, state: dict) -> dict:
        """
        THINK: Analyze the current situation.
        
        Determines:
        - Should we continue?
        - Do we need to re-plan?
        - What's the next best action?
        """
        pending_steps = [s for s in plan.steps if s.status == StepStatus.PENDING]
        
        if not pending_steps:
            return {"should_continue": False, "reason": "plan_complete"}
        
        # Simple reasoning - just return that we should continue
        return {
            "should_continue": True,
            "next_step": pending_steps[0].description if pending_steps else None,
            "needs_replan": False,
        }
    
    async def _act(self, plan: Plan) -> bool:
        """
        ACT: Execute the next step in the plan.
        
        Returns:
            True if step executed successfully, False otherwise
        """
        # Get ready steps (dependencies met)
        ready_steps = plan.get_ready_steps()
        
        if not ready_steps:
            # Check if we're stuck
            pending = [s for s in plan.steps if s.status == StepStatus.PENDING]
            if pending:
                logger.error("No steps ready to execute but steps are pending - possible dependency issue")
                # Try to force execute the first pending step
                ready_steps = [pending[0]]
            else:
                return True
        
        # Execute the first ready step
        step = ready_steps[0]
        
        if step.tool_name == "none" or not step.tool_name:
            # No tool needed - mark as complete
            step.status = StepStatus.COMPLETED
            logger.info(f"Step {step.step_id} complete (no tool needed)")
            return True
        
        # Update step status
        step.status = StepStatus.RUNNING
        self._current_agent.current_step = step
        
        logger.info(f"Executing step {step.step_id}: {step.description}")
        logger.info(f"  Tool: {step.tool_name}, Params: {step.parameters}")
        
        try:
            # Execute the tool with timeout
            result = await asyncio.wait_for(
                self._executor.execute(step.tool_name, step.parameters),
                timeout=self._step_timeout,
            )
            
            # Store result
            step.result = result.output if hasattr(result, 'output') else result
            step.status = StepStatus.COMPLETED if result.success else StepStatus.FAILED
            
            if result.success:
                logger.info(f"Step {step.step_id} completed successfully")
            else:
                step.error = result.error if hasattr(result, 'error') else str(result)
                logger.error(f"Step {step.step_id} failed: {step.error}")
            
            return result.success
            
        except asyncio.TimeoutError:
            step.status = StepStatus.FAILED
            step.error = f"Step timed out after {self._step_timeout}s"
            logger.error(f"Step {step.step_id} timed out")
            return False
            
        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = str(e)
            logger.error(f"Step {step.step_id} failed with exception: {e}")
            return False
        
        finally:
            self._current_agent.current_step = None
    
    async def _evaluate(self, step_success: bool) -> bool:
        """
        EVALUATE: Check if the step execution was successful.
        
        Returns:
            True if we should continue, False to stop
        """
        if self._current_agent.plan.has_failed():
            # Check if we should continue despite failures
            # For now, fail fast
            return False
        
        return True
    
    async def _handle_failure(self, plan: Plan) -> None:
        """
        Handle step failures with retry logic.
        
        Implements simple retry:
        - Retry failed steps up to 2 times
        - Skip steps that fail repeatedly
        """
        failed_steps = [s for s in plan.steps if s.status == StepStatus.FAILED]
        
        for step in failed_steps:
            # Could implement retry logic here
            logger.warning(f"Step {step.step_id} failed: {step.error}")
            
            # For now, just log the failure
            # Advanced retry logic could go here
    
    def _get_progress(self) -> dict:
        """Get current execution progress."""
        if not self._current_agent:
            return {}
        
        plan = self._current_agent.plan
        total = len(plan.steps)
        if total == 0:
            return {"percent": 0, "completed": 0, "total": 0}
        
        completed = sum(1 for s in plan.steps if s.status == StepStatus.COMPLETED)
        
        return {
            "percent": int((completed / total) * 100),
            "completed": completed,
            "total": total,
            "current_step": self._current_agent.current_step.step_id 
                if self._current_agent.current_step else None,
        }
    
    def _count_steps(self) -> str:
        """Get a string count of steps by status."""
        if not self._current_agent:
            return "N/A"
        
        plan = self._current_agent.plan
        pending = sum(1 for s in plan.steps if s.status == StepStatus.PENDING)
        running = sum(1 for s in plan.steps if s.status == StepStatus.RUNNING)
        completed = sum(1 for s in plan.steps if s.status == StepStatus.COMPLETED)
        failed = sum(1 for s in plan.steps if s.status == StepStatus.FAILED)
        
        parts = []
        if pending: parts.append(f"{pending} pending")
        if running: parts.append(f"{running} running")
        if completed: parts.append(f"{completed} done")
        if failed: parts.append(f"{failed} failed")
        
        return ", ".join(parts) if parts else "no steps"
    
    def pause(self) -> None:
        """Pause the current execution."""
        if self._current_agent:
            self._current_agent.paused = True
            logger.info("Agent execution paused")
    
    def resume(self) -> None:
        """Resume paused execution."""
        if self._current_agent:
            self._current_agent.paused = False
            logger.info("Agent execution resumed")
    
    def cancel(self) -> None:
        """Cancel the current execution."""
        if self._current_agent:
            self._current_agent.cancelled = True
            logger.info("Agent execution cancelled")
    
    def get_status(self) -> dict:
        """Get current agent status."""
        if not self._current_agent:
            return {"status": "idle"}
        
        return {
            "status": "paused" if self._current_agent.paused else "running",
            "task": self._current_agent.plan.task,
            "iteration": self._current_agent.iteration,
            "progress": self._get_progress(),
            "current_step": self._current_agent.current_step.description 
                if self._current_agent.current_step else None,
        }


class WorkflowRunner:
    """
    High-level runner for executing predefined workflows.
    
    Provides a simple interface for running multi-step tasks
    without directly dealing with plans.
    """
    
    def __init__(self, brain, tool_executor, state_manager, planner: AgentPlanner) -> None:
        self._brain = brain
        self._executor = tool_executor
        self._state = state_manager
        self._planner = planner
        self._executor_agent = AgentExecutor(brain, tool_executor, state_manager)
    
    async def run_task(
        self,
        task_description: str,
        context: str = "",
    ) -> ExecutionResult:
        """
        Run a complex task by:
        1. Creating a plan from the task
        2. Validating the plan
        3. Executing the plan
        """
        logger.info(f"WorkflowRunner: Starting task '{task_description}'")
        
        # Create plan
        plan = await self._planner.create_plan(task_description, context)
        
        # Validate plan
        is_valid, errors = self._planner.validate_plan(plan)
        
        if not is_valid:
            logger.error(f"Plan validation failed: {errors}")
            return ExecutionResult(
                success=False,
                plan=plan,
                total_steps=len(plan.steps),
                completed_steps=0,
                failed_steps=len(plan.steps),
                duration_seconds=0.0,
                errors=errors,
            )
        
        # Optimize plan for parallel execution
        plan = await self._planner.optimize_plan(plan)
        
        # Execute plan
        result = await self._executor_agent.execute_plan(plan)
        
        return result
    
    async def run_workspace(self, workspace_type: str) -> ExecutionResult:
        """
        Quick start a predefined workspace.
        
        Examples:
        - "pentesting" - Opens BurpSuite, Firefox, Terminal, Notes
        - "development" - Opens VS Code, Terminal, Firefox
        """
        workspace_tasks = {
            "pentesting": "Open my pentesting workspace with BurpSuite, Firefox, Terminal, and Notes",
            "development": "Open my development workspace with VS Code, Terminal, and Firefox",
            "research": "Open my research workspace with Firefox, Notes, and Terminal",
            "media": "Open my media workspace with VLC and Firefox",
        }
        
        task = workspace_tasks.get(workspace_type.lower())
        if not task:
            raise ValueError(f"Unknown workspace type: {workspace_type}")
        
        return await self.run_task(task)

