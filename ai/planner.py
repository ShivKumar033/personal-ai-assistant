"""
JARVIS AI — Agent Planner

Breaks complex user instructions into executable multi-step plans using LLM.
Implements ReAct-style (Reasoning + Acting) planning.

Usage:
    from ai.planner import AgentPlanner, Plan, PlanStep
    
    planner = AgentPlanner(brain, tool_registry)
    plan = await planner.create_plan("Prepare my pentesting environment")
"""

from __future__ import annotations

import json
import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from loguru import logger


class StepStatus(str, Enum):
    """Status of a plan step."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PlanStep:
    """A single step in an execution plan."""
    step_id: int
    description: str
    tool_name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    depends_on: list[int] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    parallel_with: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "description": self.description,
            "tool": self.tool_name,
            "parameters": self.parameters,
            "depends_on": self.depends_on,
            "status": self.status.value,
            "result": str(self.result) if self.result else None,
            "error": self.error,
        }


@dataclass
class Plan:
    """A complete execution plan with multiple steps."""
    task: str
    steps: list[PlanStep] = field(default_factory=list)
    original_request: str = ""
    context: str = ""
    created_by: str = "llm"  # "llm" or "template"
    estimated_duration: float = 0.0
    
    def get_step(self, step_id: int) -> Optional[PlanStep]:
        """Get a step by ID."""
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None
    
    def get_ready_steps(self) -> list[PlanStep]:
        """Get steps that are ready to execute (dependencies met)."""
        ready = []
        for step in self.steps:
            if step.status != StepStatus.PENDING:
                continue
            # Check if all dependencies are completed
            deps_met = all(
                (dep := self.get_step(dep_id)) is not None and dep.status == StepStatus.COMPLETED
                for dep_id in step.depends_on
            )
            if deps_met:
                ready.append(step)
        return ready
    
    def is_complete(self) -> bool:
        """Check if all steps are complete."""
        return all(s.status == StepStatus.COMPLETED for s in self.steps)
    
    def has_failed(self) -> bool:
        """Check if any step failed."""
        return any(s.status == StepStatus.FAILED for s in self.steps)
    
    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "steps": [s.to_dict() for s in self.steps],
            "original_request": self.original_request,
            "created_by": self.created_by,
            "estimated_duration": self.estimated_duration,
            "is_complete": self.is_complete(),
            "has_failed": self.has_failed(),
        }


class AgentPlanner:
    """
    LLM-based planner that decomposes complex tasks into executable plans.
    
    Uses the AI Brain to:
    1. Understand the user's complex request
    2. Break it down into discrete steps
    3. Select appropriate tools for each step
    4. Resolve dependencies between steps
    """

    # Common workspace templates
    WORKSPACE_TEMPLATES = {
        "pentesting": {
            "name": "Penetration Testing Workspace",
            "steps": [
                {"tool": "open_app", "params": {"app_name": "burpsuite"}},
                {"tool": "open_app", "params": {"app_name": "firefox"}},
                {"tool": "open_app", "params": {"app_name": "terminal"}},
                {"tool": "open_app", "params": {"app_name": "notes"}},
            ]
        },
        "development": {
            "name": "Development Workspace",
            "steps": [
                {"tool": "open_app", "params": {"app_name": "code"}},
                {"tool": "open_app", "params": {"app_name": "terminal"}},
                {"tool": "open_app", "params": {"app_name": "firefox"}},
            ]
        },
        "research": {
            "name": "Research Workspace", 
            "steps": [
                {"tool": "open_app", "params": {"app_name": "firefox"}},
                {"tool": "open_app", "params": {"app_name": "notes"}},
                {"tool": "open_app", "params": {"app_name": "terminal"}},
            ]
        },
        "media": {
            "name": "Media Workspace",
            "steps": [
                {"tool": "open_app", "params": {"app_name": "vlc"}},
                {"tool": "open_app", "params": {"app_name": "firefox"}},
            ]
        },
    }

    def __init__(self, brain, tool_registry) -> None:
        self._brain = brain
        self._registry = tool_registry
        self._max_steps = 20
        self._max_retries = 2

    async def create_plan(
        self,
        user_request: str,
        context: str = "",
        template_name: str = None,
    ) -> Plan:
        """
        Create an execution plan from a user request.
        
        Args:
            user_request: The complex task to plan
            context: Additional context (conversation history, etc.)
            template_name: Optional predefined template name
            
        Returns:
            Plan object with decomposed steps
        """
        logger.info(f"Creating plan for: {user_request}")
        
        # Check for template match first
        if template_name and template_name.lower() in self.WORKSPACE_TEMPLATES:
            return self._create_from_template(user_request, template_name.lower())
        
        # Check for keyword-based template detection
        detected_template = self._detect_template(user_request)
        if detected_template:
            return self._create_from_template(user_request, detected_template)
        
        # Use LLM to decompose the request
        return await self._create_llm_plan(user_request, context)

    def _detect_template(self, request: str) -> Optional[str]:
        """Detect if request matches a known workspace template."""
        request_lower = request.lower()
        
        template_keywords = {
            "pentesting": ["pentest", "penetration", "hacking", "security", "burp", "ethical hacking"],
            "development": ["develop", "code", "programming", "dev"],
            "research": ["research", "study", "investigate"],
            "media": ["media", "video", "music", "entertainment"],
        }
        
        for template, keywords in template_keywords.items():
            if any(kw in request_lower for kw in keywords):
                return template
        
        return None

    def _create_from_template(self, request: str, template_name: str) -> Plan:
        """Create a plan from a predefined template."""
        template = self.WORKSPACE_TEMPLATES[template_name]
        
        steps = []
        for i, step_def in enumerate(template["steps"]):
            step = PlanStep(
                step_id=i + 1,
                description=f"Open {step_def['params'].get('app_name', 'application')}",
                tool_name=step_def["tool"],
                parameters=step_def["params"],
            )
            steps.append(step)
        
        plan = Plan(
            task=template["name"],
            steps=steps,
            original_request=request,
            created_by="template",
        )
        
        logger.info(f"Created template plan: {template_name} with {len(steps)} steps")
        return plan

    async def _create_llm_plan(self, user_request: str, context: str) -> Plan:
        """Create a plan using LLM-based decomposition."""
        
        # Get available tools for the LLM
        tools = self._registry.list_tools()
        tool_schemas = [
            {
                "name": t.name,
                "description": t.description,
                "parameters": list(t.parameters.keys()),
            }
            for t in tools
        ]
        
        tools_json = json.dumps(tool_schemas, indent=2)
        
        prompt = f"""You are JARVIS, an AI planning assistant. Break down the user's request into a sequence of executable steps.

User Request: "{user_request}"

{f"Context:\n{context}" if context else ""}

Available Tools:
{tools_json}

Instructions:
1. Analyze the user's request
2. Break it down into specific, actionable steps
3. For each step, identify the appropriate tool and parameters
4. Consider dependencies (some steps may need others to complete first)
5. Output your plan as JSON

Respond ONLY with a valid JSON object in this format:
{{
    "task": "Brief description of the overall task",
    "steps": [
        {{
            "step_id": 1,
            "description": "What this step does",
            "tool": "tool_name from available tools",
            "parameters": {{"param1": "value1"}},
            "depends_on": []  # List of step_ids this depends on
        }}
    ],
    "estimated_duration_seconds": 30
}}

Important:
- Only use tools from the available tools list
- If no tool is needed for a step, set tool to "none"
- Keep steps simple and atomic
- Maximum {self._max_steps} steps
- Set depends_on to [] if the step has no dependencies
"""
        
        try:
            # Use AI Brain to generate the plan
            response = await self._brain.think(
                prompt,
                context=context,
                available_tools=tool_schemas,
            )
            
            # Parse the LLM response
            plan_data = self._parse_llm_response(response.text)
            
            if plan_data:
                steps = []
                for step_data in plan_data.get("steps", []):
                    step = PlanStep(
                        step_id=step_data.get("step_id", len(steps) + 1),
                        description=step_data.get("description", ""),
                        tool_name=step_data.get("tool", ""),
                        parameters=step_data.get("parameters", {}),
                        depends_on=step_data.get("depends_on", []),
                    )
                    steps.append(step)
                
                plan = Plan(
                    task=plan_data.get("task", user_request),
                    steps=steps,
                    original_request=user_request,
                    context=context,
                    created_by="llm",
                    estimated_duration=plan_data.get("estimated_duration_seconds", 0),
                )
                
                logger.info(f"Created LLM plan with {len(steps)} steps")
                return plan
            
        except Exception as e:
            logger.error(f"LLM planning failed: {e}")
        
        # Fallback: create a simple single-step plan
        return self._create_fallback_plan(user_request)

    def _parse_llm_response(self, response: str) -> Optional[dict]:
        """Parse JSON plan from LLM response."""
        import re
        
        # Try direct JSON parse
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        # Try extracting from markdown code blocks
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Try finding JSON object in text
        brace_match = re.search(r'\{.*\}', response, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group())
            except json.JSONDecodeError:
                pass
        
        return None

    def _create_fallback_plan(self, user_request: str) -> Plan:
        """Create a simple fallback plan when LLM fails."""
        
        # Try to infer a tool from the request
        request_lower = user_request.lower()
        tool_name = "open_app"
        params = {}
        
        if "search" in request_lower:
            tool_name = "run_shell"
            params = {"command": f"echo 'Search: {user_request}'"}
        elif "file" in request_lower or "create" in request_lower:
            tool_name = "create_file"
            params = {"path": "/tmp/jarvis_note.txt", "content": user_request}
        
        step = PlanStep(
            step_id=1,
            description=f"Execute: {user_request}",
            tool_name=tool_name,
            parameters=params,
        )
        
        return Plan(
            task=user_request,
            steps=[step],
            original_request=user_request,
            created_by="fallback",
        )

    def validate_plan(self, plan: Plan) -> tuple[bool, list[str]]:
        """
        Validate a plan before execution.
        
        Returns:
            (is_valid, error_messages)
        """
        errors = []
        
        if not plan.steps:
            errors.append("Plan has no steps")
            return False, errors
        
        if len(plan.steps) > self._max_steps:
            errors.append(f"Plan exceeds maximum steps ({self._max_steps})")
        
        # Validate each step
        step_ids = {s.step_id for s in plan.steps}
        for step in plan.steps:
            # Check tool exists
            if step.tool_name and not self._registry.exists(step.tool_name):
                errors.append(f"Step {step.step_id}: Unknown tool '{step.tool_name}'")
            
            # Check dependencies are valid
            for dep_id in step.depends_on:
                if dep_id not in step_ids:
                    errors.append(
                        f"Step {step.step_id}: Invalid dependency {dep_id}"
                    )
            
            # Check for circular dependencies
            if self._has_circular_dependency(plan, step.step_id):
                errors.append(f"Step {step.step_id}: Circular dependency detected")
        
        return len(errors) == 0, errors

    def _has_circular_dependency(self, plan: Plan, step_id: int, visited: set = None) -> bool:
        """Check for circular dependencies in a plan."""
        if visited is None:
            visited = set()
        
        if step_id in visited:
            return True
        
        visited.add(step_id)
        
        step = plan.get_step(step_id)
        if step:
            for dep_id in step.depends_on:
                if self._has_circular_dependency(plan, dep_id, visited.copy()):
                    return True
        
        return False

    async def optimize_plan(self, plan: Plan) -> Plan:
        """
        Optimize a plan for parallel execution where possible.
        
        Identifies steps that can run in parallel (no dependencies between them).
        """
        # Mark steps that can run in parallel
        for i, step in enumerate(plan.steps):
            if step.status != StepStatus.PENDING:
                continue
            
            # Find steps with no dependencies on each other
            parallel_candidates = []
            for other_step in plan.steps:
                if other_step.step_id == step.step_id:
                    continue
                if other_step.status != StepStatus.PENDING:
                    continue
                
                # Check if they depend on each other
                if (step.step_id not in other_step.depends_on and 
                    other_step.step_id not in step.depends_on):
                    parallel_candidates.append(other_step.step_id)
            
            if parallel_candidates:
                step.parallel_with = parallel_candidates[:3]  # Max 3 parallel
        
        return plan

