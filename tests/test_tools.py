"""
JARVIS AI — Tests for Tool Registry & Executor
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import SecurityConfig
from security import PermissionEngine
from tools.tool_registry import ToolRegistry
from tools.tool_executor import ToolExecutor, ExecutionStatus


@pytest.fixture
def registry() -> ToolRegistry:
    return ToolRegistry()


@pytest.fixture
def permission_engine() -> PermissionEngine:
    config = SecurityConfig(
        confirmation_required=False,  # Disable for testing
        blocked_commands=[],
        safe_commands=[],
        risk_levels={
            "system": "safe",
            "file_delete": "confirm",
        },
    )
    return PermissionEngine(config)


@pytest.fixture
def executor(registry, permission_engine) -> ToolExecutor:
    return ToolExecutor(registry, permission_engine)


class TestToolRegistry:
    """Tests for ToolRegistry."""

    def test_register_tool(self, registry):
        @registry.register(
            name="test_tool",
            description="A test tool",
            category="test",
        )
        async def test_tool(arg1: str) -> str:
            return f"Result: {arg1}"

        assert registry.exists("test_tool")
        assert registry.count == 1

    def test_get_tool(self, registry):
        @registry.register(name="my_tool", description="My tool")
        async def my_tool() -> str:
            return "hello"

        tool = registry.get("my_tool")
        assert tool is not None
        assert tool.name == "my_tool"
        assert tool.description == "My tool"

    def test_list_tools(self, registry):
        @registry.register(name="t1", description="Tool 1", category="cat_a")
        async def t1(): pass

        @registry.register(name="t2", description="Tool 2", category="cat_b")
        async def t2(): pass

        tools = registry.list_tools()
        assert len(tools) == 2

        tools_a = registry.list_tools(category="cat_a")
        assert len(tools_a) == 1
        assert tools_a[0].name == "t1"

    def test_disable_enable(self, registry):
        @registry.register(name="toggleable", description="Toggle me")
        async def toggleable(): pass

        registry.disable("toggleable")
        assert len(registry.list_tools()) == 0

        registry.enable("toggleable")
        assert len(registry.list_tools()) == 1

    def test_unregister(self, registry):
        @registry.register(name="removable", description="Remove me")
        async def removable(): pass

        assert registry.exists("removable")
        registry.unregister("removable")
        assert not registry.exists("removable")

    def test_parameter_extraction(self, registry):
        @registry.register(name="param_tool", description="Params")
        async def param_tool(name: str, count: int, flag: bool) -> str:
            return "ok"

        tool = registry.get("param_tool")
        assert "name" in tool.parameters
        assert tool.parameters["name"] == "str"
        assert tool.parameters["count"] == "int"
        assert tool.parameters["flag"] == "bool"

    def test_tool_schemas(self, registry):
        @registry.register(
            name="schema_tool",
            description="Schema test",
            category="test",
            risk_level="safe",
        )
        async def schema_tool(query: str) -> str:
            return "result"

        schemas = registry.get_tool_schemas()
        assert len(schemas) == 1
        assert schemas[0]["name"] == "schema_tool"
        assert schemas[0]["category"] == "test"


class TestToolExecutor:
    """Tests for ToolExecutor."""

    @pytest.mark.asyncio
    async def test_execute_success(self, registry, executor):
        @registry.register(
            name="greet",
            description="Greet someone",
            category="system",
        )
        async def greet(name: str) -> str:
            return f"Hello, {name}!"

        result = await executor.execute("greet", {"name": "Shiv"})
        assert result.success
        assert result.output == "Hello, Shiv!"
        assert result.status == ExecutionStatus.SUCCESS
        assert result.execution_time_ms > 0

    @pytest.mark.asyncio
    async def test_execute_nonexistent_tool(self, executor):
        result = await executor.execute("nonexistent_tool")
        assert not result.success
        assert result.status == ExecutionStatus.FAILED
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_execute_disabled_tool(self, registry, executor):
        @registry.register(name="disabled_tool", description="Disabled")
        async def disabled_tool() -> str:
            return "should not run"

        registry.disable("disabled_tool")
        result = await executor.execute("disabled_tool")
        assert not result.success
        assert "disabled" in result.error

    @pytest.mark.asyncio
    async def test_execute_timeout(self, registry, executor):
        @registry.register(
            name="slow_tool",
            description="Takes too long",
            category="system",
        )
        async def slow_tool() -> str:
            await asyncio.sleep(10)
            return "done"

        result = await executor.execute("slow_tool", timeout=0.1)
        assert not result.success
        assert result.status == ExecutionStatus.TIMEOUT

    @pytest.mark.asyncio
    async def test_execute_error_handling(self, registry, executor):
        @registry.register(
            name="broken_tool",
            description="Raises error",
            category="system",
        )
        async def broken_tool() -> str:
            raise ValueError("Something went wrong")

        result = await executor.execute("broken_tool")
        assert not result.success
        assert result.status == ExecutionStatus.FAILED
        assert "Something went wrong" in result.error

    @pytest.mark.asyncio
    async def test_execution_log(self, registry, executor):
        @registry.register(
            name="logged_tool",
            description="Logged",
            category="system",
        )
        async def logged_tool() -> str:
            return "ok"

        await executor.execute("logged_tool")
        await executor.execute("logged_tool")

        assert len(executor.execution_log) == 2
        assert executor.last_result.success

    @pytest.mark.asyncio
    async def test_sync_tool(self, registry, executor):
        """Test that synchronous tools also work."""
        @registry.register(
            name="sync_tool",
            description="Sync tool",
            category="system",
        )
        def sync_tool() -> str:
            return "sync result"

        result = await executor.execute("sync_tool")
        assert result.success
        assert result.output == "sync result"

    @pytest.mark.asyncio
    async def test_batch_sequential(self, registry, executor):
        @registry.register(name="add", description="Add", category="system")
        async def add(a: int, b: int) -> int:
            return a + b

        tasks = [
            {"tool": "add", "params": {"a": 1, "b": 2}},
            {"tool": "add", "params": {"a": 3, "b": 4}},
        ]
        results = await executor.execute_batch(tasks, parallel=False)
        assert len(results) == 2
        assert results[0].output == 3
        assert results[1].output == 7
