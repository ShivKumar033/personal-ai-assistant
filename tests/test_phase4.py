"""
JARVIS AI — Tests for Phase 4: Agent System & Task Planning
"""

import asyncio
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai.planner import AgentPlanner, Plan, PlanStep, StepStatus
from ai.agent_executor import AgentExecutor, ExecutionResult, WorkflowRunner
from core.task_orchestrator import TaskOrchestrator, ScheduledTask, QueuedTask
from agents.base_agent import BaseAgent, AgentResult
from agents import ResearchAgent, AutomationAgent, SystemAgent, FileAgent, CodingAgent


# ── Fixtures ──────────────────────────────────────────────

@pytest.fixture
def mock_brain():
    brain = MagicMock()
    brain.think = AsyncMock()
    # Mock specific for agent tests 
    mock_llm_response = MagicMock()
    mock_llm_response.text = '{"task": "test", "steps": [{"step_id": 1, "description": "do it", "tool": "mock_tool", "parameters": {}}]}'
    brain.think.return_value = mock_llm_response
    brain.router = MagicMock()
    brain.router.route_task.return_value = MagicMock(chat=AsyncMock(return_value=mock_llm_response.text))
    return brain

@pytest.fixture
def mock_registry():
    registry = MagicMock()
    registry.list_tools.return_value = []
    registry.exists.return_value = True
    return registry

@pytest.fixture
def mock_tool_executor():
    executor = MagicMock()
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.output = "Success"
    executor.execute = AsyncMock(return_value=mock_result)
    return executor

@pytest.fixture
def mock_state_manager():
    state = MagicMock()
    state.summary.return_value = {"cpu": 10, "mem": 20}
    return state


# ═════════════════════════════════════════════════════════════
#  Agent Planner Tests
# ═════════════════════════════════════════════════════════════

class TestAgentPlanner:
    
    @pytest.mark.asyncio
    async def test_detect_template(self, mock_brain, mock_registry):
        planner = AgentPlanner(mock_brain, mock_registry)
        
        assert planner._detect_template("prepare my pentesting workspace") == "pentesting"
        assert planner._detect_template("start development mode") == "development"
        assert planner._detect_template("do some research") == "research"
        assert planner._detect_template("play some media") == "media"
        assert planner._detect_template("do unknown task") is None

    @pytest.mark.asyncio
    async def test_create_template_plan(self, mock_brain, mock_registry):
        planner = AgentPlanner(mock_brain, mock_registry)
        plan = await planner.create_plan("prepare pentesting workspace")
        
        assert plan.created_by == "template"
        assert plan.task == "Penetration Testing Workspace"
        assert len(plan.steps) == 4
        # burpsuite, firefox, terminal, notes
        tool_params = [s.parameters.get("app_name") for s in plan.steps]
        assert "burpsuite" in tool_params
        assert "firefox" in tool_params

    @pytest.mark.asyncio
    async def test_plan_validation(self, mock_brain, mock_registry):
        planner = AgentPlanner(mock_brain, mock_registry)
        
        # Valid plan
        plan = Plan(task="test", steps=[PlanStep(step_id=1, description="step 1", tool_name="valid")])
        valid, errors = planner.validate_plan(plan)
        assert valid is True
        
        # Invalid dependency
        plan2 = Plan(task="test", steps=[PlanStep(step_id=1, description="step 1", tool_name="valid", depends_on=[99])])
        valid2, errors2 = planner.validate_plan(plan2)
        assert valid2 is False
        assert any("Invalid dependency 99" in str(e) for e in errors2)
        
        # Circular dependency
        s1 = PlanStep(step_id=1, description="a", tool_name="t", depends_on=[2])
        s2 = PlanStep(step_id=2, description="b", tool_name="t", depends_on=[1])
        plan3 = Plan(task="test", steps=[s1, s2])
        valid3, errors3 = planner.validate_plan(plan3)
        assert valid3 is False
        assert any("Circular dependency" in str(e) for e in errors3)


# ═════════════════════════════════════════════════════════════
#  Agent Executor Tests
# ═════════════════════════════════════════════════════════════

class TestAgentExecutor:

    @pytest.mark.asyncio
    async def test_execute_plan_success(self, mock_brain, mock_tool_executor, mock_state_manager):
        executor = AgentExecutor(mock_brain, mock_tool_executor, mock_state_manager)
        
        plan = Plan(task="test", steps=[
            PlanStep(step_id=1, description="step 1", tool_name="valid")
        ])
        
        result = await executor.execute_plan(plan, show_progress=False)
        assert result.success is True
        assert result.completed_steps == 1
        assert plan.steps[0].status == StepStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_plan_no_tool(self, mock_brain, mock_tool_executor, mock_state_manager):
        executor = AgentExecutor(mock_brain, mock_tool_executor, mock_state_manager)
        
        plan = Plan(task="test", steps=[
            PlanStep(step_id=1, description="no tool step", tool_name="none")
        ])
        
        result = await executor.execute_plan(plan, show_progress=False)
        assert result.success is True
        # Executor method shouldn't be called for "none" tool
        assert mock_tool_executor.execute.call_count == 0


# ═════════════════════════════════════════════════════════════
#  Specialized Agents Tests
# ═════════════════════════════════════════════════════════════

class TestAgents:

    @pytest.mark.asyncio
    async def test_research_agent(self, mock_brain, mock_tool_executor):
        agent = ResearchAgent(mock_brain, mock_tool_executor)
        result = await agent.execute("What is Quantum Computing?")
        assert result.success is True
        assert mock_brain.think.call_count == 2
        assert result.agent_name == "research_agent"

    @pytest.mark.asyncio
    async def test_system_agent(self, mock_brain, mock_tool_executor):
        agent = SystemAgent(mock_brain, mock_tool_executor)
        result = await agent.execute("Disable the firewall")
        assert result.success is True
        assert result.agent_name == "system_agent"

    @pytest.mark.asyncio
    async def test_file_agent(self, mock_brain, mock_tool_executor):
        agent = FileAgent(mock_brain, mock_tool_executor)
        result = await agent.execute("Organize my downloads folder")
        assert result.success is True
        # FileAgent directly calls organize_folder
        mock_tool_executor.execute.assert_called_once()
        assert mock_tool_executor.execute.call_args[0][0] == "organize_folder"


# ═════════════════════════════════════════════════════════════
#  Task Orchestrator Tests
# ═════════════════════════════════════════════════════════════

class TestTaskOrchestrator:

    @pytest.mark.asyncio
    async def test_enqueue_task(self):
        runner = MagicMock()
        orch = TaskOrchestrator(runner)
        
        tid = orch.enqueue("do work", priority=1)
        assert len(orch._queue) == 1
        assert orch._queue[0].id == tid
        assert orch._queue[0].status == "pending"

    @pytest.mark.asyncio
    async def test_schedule_task(self):
        runner = MagicMock()
        orch = TaskOrchestrator(runner)
        
        action = AsyncMock()
        orch.schedule("daily_job", "0 9 * * *", action, param="fast")
        
        assert "daily_job" in orch._schedules
        task = orch._schedules["daily_job"]
        assert task.cron_expr == "0 9 * * *"
        assert task.kwargs["param"] == "fast"

    @pytest.mark.asyncio
    async def test_orchestrator_start_stop(self):
        runner = MagicMock()
        orch = TaskOrchestrator(runner)
        
        await orch.start()
        assert orch._is_running is True
        assert orch._loop_task is not None
        
        await orch.stop()
        await asyncio.sleep(0.01)
        assert orch._is_running is False
        assert orch._loop_task.cancelled()
