"""
JARVIS AI — Tests for Phase 3: System Control, File Manager, Automation
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.tool_registry import ToolRegistry
from tools.tool_executor import ToolExecutor
from security import PermissionEngine


# ── Fixtures ──────────────────────────────────────────────

@pytest.fixture
def registry():
    """Create a ToolRegistry with all Phase 3 tools."""
    reg = ToolRegistry()
    from tools.builtin_tools import register_builtin_tools
    register_builtin_tools(reg)
    return reg


@pytest.fixture
def executor(registry):
    """Create a ToolExecutor with a permissive security config."""
    from config import SecurityConfig
    config = SecurityConfig(
        confirmation_required=False,
        risk_levels={
            "system": "safe",
            "file": "safe",
            "automation": "safe",
            "web": "safe",
            "info": "safe",
            "general": "safe",
        },
    )
    perm = PermissionEngine(config)
    return ToolExecutor(registry, perm)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for file tests."""
    with tempfile.TemporaryDirectory(prefix="jarvis_test_") as tmpdir:
        yield tmpdir


# ═════════════════════════════════════════════════════════════
#  Tool Registration Tests
# ═════════════════════════════════════════════════════════════

class TestToolRegistration:
    """Verify all Phase 3 tools are properly registered."""

    def test_total_tool_count(self, registry):
        """At least 25+ tools should be registered (Phase 1 + Phase 3)."""
        assert registry.count >= 25

    def test_system_control_tools(self, registry):
        """System control tools are registered."""
        system_tools = [
            "open_app", "close_app", "run_shell", "kill_process",
            "clipboard_copy", "clipboard_paste", "open_url",
            "lock_screen", "take_screenshot",
        ]
        for tool_name in system_tools:
            assert registry.exists(tool_name), f"Missing tool: {tool_name}"

    def test_file_manager_tools(self, registry):
        """File manager tools are registered."""
        file_tools = [
            "create_file", "read_file", "move_file", "copy_file",
            "rename_file", "delete_file", "list_directory",
            "file_info", "search_files", "organize_folder",
            "create_directory", "folder_size",
        ]
        for tool_name in file_tools:
            assert registry.exists(tool_name), f"Missing tool: {tool_name}"

    def test_automation_tools(self, registry):
        """Automation tools are registered."""
        auto_tools = [
            "type_text", "press_key", "active_window",
            "focus_window", "notify",
        ]
        for tool_name in auto_tools:
            assert registry.exists(tool_name), f"Missing tool: {tool_name}"

    def test_phase1_tools_still_exist(self, registry):
        """Phase 1 tools are not broken."""
        phase1_tools = [
            "system_info", "list_processes", "current_time",
            "disk_space", "network_info", "battery_info", "system_uptime",
        ]
        for tool_name in phase1_tools:
            assert registry.exists(tool_name), f"Phase 1 tool missing: {tool_name}"

    def test_tool_schemas(self, registry):
        """All tools produce valid schemas for LLM function calling."""
        schemas = registry.get_tool_schemas()
        assert len(schemas) >= 25
        for schema in schemas:
            assert "name" in schema
            assert "description" in schema

    def test_tool_categories(self, registry):
        """Tools span multiple categories."""
        tools = registry.list_tools()
        categories = {t.category for t in tools}
        assert "system" in categories
        assert "file" in categories
        assert "automation" in categories
        assert "info" in categories


# ═════════════════════════════════════════════════════════════
#  File Manager Tests (safe to run — uses temp directory)
# ═════════════════════════════════════════════════════════════

class TestFileManager:

    @pytest.mark.asyncio
    async def test_create_file(self, executor, temp_dir):
        """Test creating a new file."""
        filepath = os.path.join(temp_dir, "test.txt")
        result = await executor.execute(
            "create_file", {"path": filepath, "content": "Hello, JARVIS!"}
        )
        assert result.success
        assert result.output["status"] == "created"
        assert Path(filepath).exists()
        assert Path(filepath).read_text() == "Hello, JARVIS!"

    @pytest.mark.asyncio
    async def test_create_file_exists_no_overwrite(self, executor, temp_dir):
        """Test that create_file rejects existing files without overwrite."""
        filepath = os.path.join(temp_dir, "existing.txt")
        Path(filepath).write_text("original")

        result = await executor.execute(
            "create_file", {"path": filepath}
        )
        assert result.success  # Tool executes, but returns status
        assert result.output["status"] == "exists"

    @pytest.mark.asyncio
    async def test_create_file_with_overwrite(self, executor, temp_dir):
        filepath = os.path.join(temp_dir, "overwrite.txt")
        Path(filepath).write_text("old content")

        result = await executor.execute(
            "create_file", {"path": filepath, "content": "new", "overwrite": True}
        )
        assert result.success
        assert result.output["status"] == "created"
        assert Path(filepath).read_text() == "new"

    @pytest.mark.asyncio
    async def test_read_file(self, executor, temp_dir):
        """Test reading a file."""
        filepath = os.path.join(temp_dir, "read_me.txt")
        Path(filepath).write_text("Line 1\nLine 2\nLine 3")

        result = await executor.execute(
            "read_file", {"path": filepath}
        )
        assert result.success
        assert result.output["status"] == "ok"
        assert "Line 1" in result.output["content"]
        assert result.output["lines"] == 3

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, executor, temp_dir):
        filepath = os.path.join(temp_dir, "nope.txt")
        result = await executor.execute(
            "read_file", {"path": filepath}
        )
        assert result.success
        assert result.output["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_move_file(self, executor, temp_dir):
        """Test moving a file."""
        src = os.path.join(temp_dir, "source.txt")
        dst = os.path.join(temp_dir, "moved.txt")
        Path(src).write_text("move me")

        result = await executor.execute(
            "move_file", {"source": src, "destination": dst}
        )
        assert result.success
        assert result.output["status"] == "moved"
        assert not Path(src).exists()
        assert Path(dst).exists()
        assert Path(dst).read_text() == "move me"

    @pytest.mark.asyncio
    async def test_copy_file(self, executor, temp_dir):
        """Test copying a file."""
        src = os.path.join(temp_dir, "original.txt")
        dst = os.path.join(temp_dir, "copy.txt")
        Path(src).write_text("copy me")

        result = await executor.execute(
            "copy_file", {"source": src, "destination": dst}
        )
        assert result.success
        assert result.output["status"] == "copied"
        assert Path(src).exists()   # Original still there
        assert Path(dst).exists()
        assert Path(dst).read_text() == "copy me"

    @pytest.mark.asyncio
    async def test_rename_file(self, executor, temp_dir):
        """Test renaming a file."""
        filepath = os.path.join(temp_dir, "old_name.txt")
        Path(filepath).write_text("rename me")

        result = await executor.execute(
            "rename_file", {"path": filepath, "new_name": "new_name.txt"}
        )
        assert result.success
        assert result.output["status"] == "renamed"
        assert not Path(filepath).exists()
        assert Path(os.path.join(temp_dir, "new_name.txt")).exists()

    @pytest.mark.asyncio
    async def test_delete_file(self, executor, temp_dir):
        """Test deleting a file."""
        filepath = os.path.join(temp_dir, "delete_me.txt")
        Path(filepath).write_text("goodbye")

        result = await executor.execute(
            "delete_file", {"path": filepath}
        )
        assert result.success
        assert result.output["status"] == "deleted"
        assert not Path(filepath).exists()

    @pytest.mark.asyncio
    async def test_delete_directory(self, executor, temp_dir):
        """Test deleting a directory."""
        dirpath = os.path.join(temp_dir, "subdir")
        os.makedirs(dirpath)
        Path(os.path.join(dirpath, "file.txt")).write_text("x")

        result = await executor.execute(
            "delete_file", {"path": dirpath}
        )
        assert result.success
        assert result.output["status"] == "deleted"
        assert result.output["type"] == "directory"

    @pytest.mark.asyncio
    async def test_list_directory(self, executor, temp_dir):
        """Test listing directory contents."""
        # Create some test files
        Path(os.path.join(temp_dir, "file1.txt")).write_text("a")
        Path(os.path.join(temp_dir, "file2.py")).write_text("b")
        Path(os.path.join(temp_dir, ".hidden")).write_text("c")
        os.makedirs(os.path.join(temp_dir, "subdir"))

        result = await executor.execute(
            "list_directory", {"path": temp_dir}
        )
        assert result.success
        assert result.output["status"] == "ok"

        names = [i["name"] for i in result.output["items"]]
        assert "file1.txt" in names
        assert "file2.py" in names
        assert "subdir" in names
        # Hidden files excluded by default
        assert ".hidden" not in names

    @pytest.mark.asyncio
    async def test_list_directory_show_hidden(self, executor, temp_dir):
        Path(os.path.join(temp_dir, ".hidden")).write_text("c")

        result = await executor.execute(
            "list_directory", {"path": temp_dir, "show_hidden": True}
        )
        names = [i["name"] for i in result.output["items"]]
        assert ".hidden" in names

    @pytest.mark.asyncio
    async def test_file_info(self, executor, temp_dir):
        """Test getting file information."""
        filepath = os.path.join(temp_dir, "info_test.py")
        Path(filepath).write_text("print('hello')")

        result = await executor.execute(
            "file_info", {"path": filepath}
        )
        assert result.success
        assert result.output["status"] == "ok"
        assert result.output["name"] == "info_test.py"
        assert result.output["extension"] == ".py"
        assert result.output["category"] == "Code"
        assert "md5" in result.output  # File < 50MB
        assert result.output["type"] == "file"

    @pytest.mark.asyncio
    async def test_search_files(self, executor, temp_dir):
        """Test searching for files."""
        Path(os.path.join(temp_dir, "report.pdf")).write_text("fake pdf")
        Path(os.path.join(temp_dir, "notes.txt")).write_text("notes")
        subdir = os.path.join(temp_dir, "sub")
        os.makedirs(subdir)
        Path(os.path.join(subdir, "deep_report.pdf")).write_text("deep")

        result = await executor.execute(
            "search_files", {"pattern": "*.pdf", "directory": temp_dir}
        )
        assert result.success
        assert result.output["matches"] == 2
        names = [r["name"] for r in result.output["results"]]
        assert "report.pdf" in names
        assert "deep_report.pdf" in names

    @pytest.mark.asyncio
    async def test_organize_folder_dry_run(self, executor, temp_dir):
        """Test folder organization in dry-run mode."""
        Path(os.path.join(temp_dir, "photo.jpg")).write_text("img")
        Path(os.path.join(temp_dir, "report.pdf")).write_text("doc")
        Path(os.path.join(temp_dir, "script.py")).write_text("code")
        Path(os.path.join(temp_dir, "song.mp3")).write_text("audio")

        result = await executor.execute(
            "organize_folder", {"path": temp_dir, "dry_run": True}
        )
        assert result.success
        assert result.output["status"] == "preview"
        assert result.output["files_moved"] == 4

        # Verify files were NOT actually moved (dry run)
        assert Path(os.path.join(temp_dir, "photo.jpg")).exists()

    @pytest.mark.asyncio
    async def test_organize_folder_real(self, executor, temp_dir):
        """Test actual folder organization."""
        Path(os.path.join(temp_dir, "photo.jpg")).write_text("img")
        Path(os.path.join(temp_dir, "report.pdf")).write_text("doc")
        Path(os.path.join(temp_dir, "script.py")).write_text("code")

        result = await executor.execute(
            "organize_folder", {"path": temp_dir}
        )
        assert result.success
        assert result.output["status"] == "organized"
        assert result.output["files_moved"] == 3

        # Verify files were moved
        assert Path(os.path.join(temp_dir, "Images", "photo.jpg")).exists()
        assert Path(os.path.join(temp_dir, "Documents", "report.pdf")).exists()
        assert Path(os.path.join(temp_dir, "Code", "script.py")).exists()

    @pytest.mark.asyncio
    async def test_create_directory(self, executor, temp_dir):
        """Test creating a new directory."""
        new_dir = os.path.join(temp_dir, "a", "b", "c")
        result = await executor.execute(
            "create_directory", {"path": new_dir}
        )
        assert result.success
        assert result.output["status"] == "created"
        assert Path(new_dir).is_dir()

    @pytest.mark.asyncio
    async def test_folder_size(self, executor, temp_dir):
        """Test folder size calculation."""
        Path(os.path.join(temp_dir, "file1.txt")).write_text("a" * 1000)
        Path(os.path.join(temp_dir, "file2.txt")).write_text("b" * 2000)
        subdir = os.path.join(temp_dir, "sub")
        os.makedirs(subdir)
        Path(os.path.join(subdir, "file3.txt")).write_text("c" * 500)

        result = await executor.execute(
            "folder_size", {"path": temp_dir}
        )
        assert result.success
        assert result.output["status"] == "ok"
        assert result.output["files"] == 3
        assert result.output["directories"] == 1
        assert result.output["total_bytes"] >= 3500
        assert len(result.output["largest_files"]) >= 1


# ═════════════════════════════════════════════════════════════
#  System Control Tests
# ═════════════════════════════════════════════════════════════

class TestSystemControl:

    @pytest.mark.asyncio
    async def test_open_url(self, executor):
        """Test open_url tool exists and has correct metadata."""
        tool = executor._registry.get("open_url")
        assert tool is not None
        assert tool.category == "web"
        assert tool.risk_level == "safe"

    @pytest.mark.asyncio
    async def test_run_shell_echo(self, executor):
        """Test running a safe shell command."""
        result = await executor.execute(
            "run_shell", {"command": "echo 'Hello from JARVIS'"}
        )
        assert result.success
        assert result.output["status"] == "completed"
        assert "Hello from JARVIS" in result.output["stdout"]
        assert result.output["return_code"] == 0

    @pytest.mark.asyncio
    async def test_run_shell_ls(self, executor):
        """Test running ls command."""
        result = await executor.execute(
            "run_shell", {"command": "ls /tmp", "timeout": 5}
        )
        assert result.success
        assert result.output["status"] == "completed"
        assert result.output["success"] is True

    @pytest.mark.asyncio
    async def test_run_shell_timeout(self, executor):
        """Test shell command timeout."""
        result = await executor.execute(
            "run_shell", {"command": "sleep 60", "timeout": 1}
        )
        assert result.success  # Tool itself doesn't fail
        assert result.output["status"] == "timeout"

    @pytest.mark.asyncio
    async def test_run_shell_failing_command(self, executor):
        """Test handling a failing command."""
        result = await executor.execute(
            "run_shell", {"command": "ls /nonexistent_path_xyz"}
        )
        assert result.success
        assert result.output["return_code"] != 0

    @pytest.mark.asyncio
    async def test_kill_nonexistent_process(self, executor):
        """Test killing a process that doesn't exist."""
        result = await executor.execute(
            "kill_process", {"pid": 999999999}
        )
        assert result.success
        assert result.output["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_close_nonexistent_app(self, executor):
        """Test closing an app that isn't running."""
        result = await executor.execute(
            "close_app", {"app_name": "nonexistent_app_xyz_12345"}
        )
        assert result.success
        assert result.output["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_open_app_not_found(self, executor):
        """Test opening an app that doesn't exist."""
        result = await executor.execute(
            "open_app", {"app_name": "totally_fake_app_xyz_99999"}
        )
        assert result.success
        assert result.output["status"] == "not_found"


# ═════════════════════════════════════════════════════════════
#  Integration Tests
# ═════════════════════════════════════════════════════════════

class TestIntegration:

    @pytest.mark.asyncio
    async def test_create_read_delete_workflow(self, executor, temp_dir):
        """Test a full create → read → delete workflow."""
        filepath = os.path.join(temp_dir, "workflow.txt")

        # Create
        r1 = await executor.execute(
            "create_file",
            {"path": filepath, "content": "JARVIS workflow test"},
        )
        assert r1.success and r1.output["status"] == "created"

        # Read
        r2 = await executor.execute("read_file", {"path": filepath})
        assert r2.success and "JARVIS workflow test" in r2.output["content"]

        # Info
        r3 = await executor.execute("file_info", {"path": filepath})
        assert r3.success and r3.output["category"] == "Documents"

        # Delete
        r4 = await executor.execute("delete_file", {"path": filepath})
        assert r4.success and r4.output["status"] == "deleted"

        # Verify deleted
        r5 = await executor.execute("read_file", {"path": filepath})
        assert r5.output["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_create_copy_rename_workflow(self, executor, temp_dir):
        """Test create → copy → rename → verify workflow."""
        original = os.path.join(temp_dir, "original.md")
        copy_path = os.path.join(temp_dir, "backup.md")

        # Create
        await executor.execute(
            "create_file",
            {"path": original, "content": "# JARVIS Notes"},
        )

        # Copy
        r1 = await executor.execute(
            "copy_file",
            {"source": original, "destination": copy_path},
        )
        assert r1.success

        # Rename the copy
        r2 = await executor.execute(
            "rename_file",
            {"path": copy_path, "new_name": "backup_v2.md"},
        )
        assert r2.success

        # Verify: original exists, renamed copy exists
        assert Path(original).exists()
        assert Path(os.path.join(temp_dir, "backup_v2.md")).exists()
        assert not Path(copy_path).exists()

    @pytest.mark.asyncio
    async def test_shell_and_file_workflow(self, executor, temp_dir):
        """Test combining shell execution with file operations."""
        # Use shell to create a file
        filepath = os.path.join(temp_dir, "shell_made.txt")
        r1 = await executor.execute(
            "run_shell",
            {"command": f"echo 'Created by shell' > {filepath}"},
        )
        assert r1.success

        # Read it with file tool
        r2 = await executor.execute("read_file", {"path": filepath})
        assert r2.success
        assert "Created by shell" in r2.output["content"]

    @pytest.mark.asyncio
    async def test_interpreter_routes_to_phase3_tools(self):
        """Test that CommandInterpreter routes to Phase 3 tools."""
        from core.command_interpreter import CommandInterpreter

        reg = ToolRegistry()
        from tools.builtin_tools import register_builtin_tools
        register_builtin_tools(reg)

        interp = CommandInterpreter(brain=None, registry=reg)

        # Direct tool match
        r1 = await interp.interpret("open_app firefox")
        assert r1.tool_name == "open_app"
        assert r1.source == "direct"

        # Keyword match → open_app
        r2 = await interp.interpret("open firefox")
        assert r2.intent == "open_app"
        assert r2.source == "keyword"

        # Direct tool match → create_file
        r3 = await interp.interpret("create_file /tmp/test.txt")
        assert r3.tool_name == "create_file"

        # Direct tool match → run_shell
        r4 = await interp.interpret("run_shell ls -la")
        assert r4.tool_name == "run_shell"
