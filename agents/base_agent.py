"""
JARVIS AI — Base Agent (Phase 4)
Interface for all specialized agents in the Multi-Agent System.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict

from loguru import logger
from dataclasses import dataclass

@dataclass
class AgentResult:
    """Result returned by an agent after executing a task."""
    success: bool
    output: Any
    error: str = None
    agent_name: str = "base"


class BaseAgent(ABC):
    """
    Base class for specific agents.
    Each agent uses the AIBrain and ToolExecutor to accomplish a specialized task.
    """
    
    name: str = "base_agent"
    description: str = "Base agent interface"
    
    def __init__(self, brain, tool_executor):
        self.brain = brain
        self.executor = tool_executor

    @abstractmethod
    async def execute(self, task: str, context: Dict[str, Any] = None) -> AgentResult:
        """Execute the agent's specialized task."""
        pass
