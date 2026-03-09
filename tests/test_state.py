"""
JARVIS AI — Tests for State Manager
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.state_manager import StateManager, JarvisStatus


@pytest.fixture(autouse=True)
def reset_state():
    """Reset singleton state before each test."""
    state = StateManager()
    state.reset()
    yield state


class TestStateManager:
    """Tests for StateManager."""

    def test_singleton(self):
        s1 = StateManager()
        s2 = StateManager()
        assert s1 is s2

    def test_initial_status(self, reset_state):
        assert reset_state.status == JarvisStatus.BOOTING

    def test_status_change(self, reset_state):
        reset_state.status = JarvisStatus.IDLE
        assert reset_state.status == JarvisStatus.IDLE

    def test_key_value_state(self, reset_state):
        reset_state.set("test_key", "test_value")
        assert reset_state.get("test_key") == "test_value"
        assert reset_state.get("nonexistent", "default") == "default"

    def test_delete_state(self, reset_state):
        reset_state.set("key", "value")
        reset_state.delete("key")
        assert reset_state.get("key") is None

    def test_task_tracking(self, reset_state):
        reset_state.register_task("task1", "Test task")
        assert len(reset_state.active_tasks) == 1
        assert "task1" in reset_state.active_tasks

        reset_state.complete_task("task1", "done")
        assert len(reset_state.active_tasks) == 0

    def test_command_history(self, reset_state):
        reset_state.log_command("test cmd", "ok", True)
        assert len(reset_state.command_history) == 1
        assert reset_state.last_command["command"] == "test cmd"
        assert reset_state.last_command["success"] is True

    def test_system_info(self, reset_state):
        info = reset_state.system_info
        assert info.os_name in ("Linux", "Windows", "Darwin")
        assert info.cpu_count > 0
        assert info.total_memory_gb > 0

    def test_resource_snapshot(self, reset_state):
        resources = reset_state.get_resources()
        assert 0 <= resources.cpu_percent <= 100
        assert 0 <= resources.memory_percent <= 100

    def test_summary(self, reset_state):
        reset_state.status = JarvisStatus.IDLE
        summary = reset_state.summary()
        assert summary["status"] == "idle"
        assert "resources" in summary
        assert "system" in summary
