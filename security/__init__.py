"""
JARVIS AI — Security & Permission Engine

Protects the system from dangerous commands by enforcing
three permission levels: safe, confirm, blocked.

Usage:
    from security.permission_engine import PermissionEngine
    engine = PermissionEngine(settings.security)
    result = await engine.check_command("rm -rf /")
    # → PermissionResult(allowed=False, level=BLOCKED, reason="...")
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from loguru import logger


class RiskLevel(str, Enum):
    """Permission risk levels."""
    SAFE = "safe"
    CONFIRM = "confirm"
    BLOCKED = "blocked"


@dataclass
class PermissionResult:
    """Result of a permission check."""
    allowed: bool
    level: RiskLevel
    reason: str
    requires_confirmation: bool = False

    def __bool__(self) -> bool:
        return self.allowed


class PermissionEngine:
    """
    Security guard for JARVIS command execution.

    Evaluates commands against:
    1. Blocked command patterns (always denied)
    2. Safe command whitelist (always allowed)
    3. Risk level mappings by category
    4. Dangerous pattern heuristics
    """

    # Patterns that indicate potentially dangerous operations
    DANGEROUS_PATTERNS = [
        r"rm\s+(-rf?|--recursive)\s+[/~]",     # recursive delete from root/home
        r"mkfs\.",                                # format filesystem
        r"dd\s+if=",                              # disk overwrite
        r">\s*/dev/sd[a-z]",                      # write to raw device
        r"chmod\s+777\s+/",                       # insecure perms on root
        r"curl\s+.*\|\s*(ba)?sh",                 # pipe curl to shell
        r"wget\s+.*\|\s*(ba)?sh",                 # pipe wget to shell
        r":\(\)\{.*\}",                           # fork bomb
        r"shutdown|reboot|poweroff",              # system power
        r"kill\s+-9\s+1\b",                       # kill init/systemd
        r"format\s+[a-z]:",                       # Windows format
        r"del\s+/[sf]\s+/q\s+[a-z]:\\",           # Windows recursive delete
        r"reg\s+delete",                          # Windows registry delete
    ]

    # Patterns that are always safe
    SAFE_PATTERNS = [
        r"^(ls|dir|pwd|echo|date|whoami|hostname|uname|cat|head|tail|wc)\b",
        r"^(python|python3)\s+--version",
        r"^pip\s+(list|show)",
    ]

    def __init__(self, security_config) -> None:
        """
        Initialize with security configuration.

        Args:
            security_config: SecurityConfig from settings
        """
        self._config = security_config
        self._blocked_commands: list[str] = security_config.blocked_commands
        self._safe_commands: list[str] = security_config.safe_commands
        self._risk_levels: dict[str, str] = security_config.risk_levels
        self._confirmation_required: bool = security_config.confirmation_required
        self._audit_log: list[dict] = []

        # Compile dangerous patterns for performance
        self._dangerous_re = [
            re.compile(p, re.IGNORECASE) for p in self.DANGEROUS_PATTERNS
        ]
        self._safe_re = [
            re.compile(p, re.IGNORECASE) for p in self.SAFE_PATTERNS
        ]

        logger.debug(
            f"PermissionEngine initialized: "
            f"{len(self._blocked_commands)} blocked, "
            f"{len(self._safe_commands)} safe commands"
        )

    # ── Public API ────────────────────────────────────────

    async def check_command(self, command: str) -> PermissionResult:
        """
        Evaluate a command string and return permission result.

        Args:
            command: The raw command string to evaluate

        Returns:
            PermissionResult with allow/deny decision and reason
        """
        command = command.strip()

        # 1. Check blocked list (exact match)
        if self._is_blocked(command):
            result = PermissionResult(
                allowed=False,
                level=RiskLevel.BLOCKED,
                reason=f"Command is explicitly blocked: '{command[:50]}'"
            )
            self._log_check(command, result)
            return result

        # 2. Check dangerous patterns (regex)
        danger_match = self._matches_dangerous_pattern(command)
        if danger_match:
            result = PermissionResult(
                allowed=False,
                level=RiskLevel.BLOCKED,
                reason=f"Command matches dangerous pattern: {danger_match}"
            )
            self._log_check(command, result)
            return result

        # 3. Check safe list (exact match or prefix)
        if self._is_safe(command):
            result = PermissionResult(
                allowed=True,
                level=RiskLevel.SAFE,
                reason="Command is in safe list"
            )
            self._log_check(command, result)
            return result

        # 4. Check safe patterns (regex)
        if self._matches_safe_pattern(command):
            result = PermissionResult(
                allowed=True,
                level=RiskLevel.SAFE,
                reason="Command matches safe pattern"
            )
            self._log_check(command, result)
            return result

        # 5. Default: require confirmation
        if self._confirmation_required:
            result = PermissionResult(
                allowed=True,
                level=RiskLevel.CONFIRM,
                reason="Command requires user confirmation",
                requires_confirmation=True
            )
        else:
            result = PermissionResult(
                allowed=True,
                level=RiskLevel.SAFE,
                reason="Confirmation disabled — auto-approved"
            )

        self._log_check(command, result)
        return result

    async def check_tool(
        self, tool_name: str, category: Optional[str] = None
    ) -> PermissionResult:
        """
        Check permission for a registered tool execution.

        Args:
            tool_name: Name of the tool to check
            category: Tool category (e.g., 'file_delete', 'app_open')

        Returns:
            PermissionResult for the tool
        """
        if category and category in self._risk_levels:
            level_str = self._risk_levels[category]
            level = RiskLevel(level_str)

            if level == RiskLevel.BLOCKED:
                return PermissionResult(
                    allowed=False,
                    level=RiskLevel.BLOCKED,
                    reason=f"Tool category '{category}' is blocked"
                )
            elif level == RiskLevel.CONFIRM:
                return PermissionResult(
                    allowed=True,
                    level=RiskLevel.CONFIRM,
                    reason=f"Tool '{tool_name}' requires confirmation",
                    requires_confirmation=True,
                )
            else:
                return PermissionResult(
                    allowed=True,
                    level=RiskLevel.SAFE,
                    reason=f"Tool '{tool_name}' is safe to execute"
                )

        # Default to confirm for unknown tools
        return PermissionResult(
            allowed=True,
            level=RiskLevel.CONFIRM,
            reason=f"Unknown tool '{tool_name}' — confirmation required",
            requires_confirmation=True,
        )

    async def request_confirmation(self, action: str) -> bool:
        """
        Request user confirmation for a sensitive action.

        Args:
            action: Description of the action to confirm

        Returns:
            True if user approves, False otherwise
        """
        logger.warning(f"Confirmation required: {action}")
        print(f"\n⚠️  JARVIS needs confirmation:")
        print(f"   Action: {action}")

        try:
            response = input("   Approve? [y/N]: ").strip().lower()
            approved = response in ("y", "yes")
            if approved:
                logger.info(f"User approved: {action}")
            else:
                logger.info(f"User denied: {action}")
            return approved
        except (EOFError, KeyboardInterrupt):
            logger.info(f"Confirmation interrupted for: {action}")
            return False

    # ── Audit Log ─────────────────────────────────────────

    @property
    def audit_log(self) -> list[dict]:
        """Get audit log of all permission checks."""
        return list(self._audit_log)

    def clear_audit_log(self) -> None:
        """Clear audit log."""
        self._audit_log.clear()

    # ── Private Methods ───────────────────────────────────

    def _is_blocked(self, command: str) -> bool:
        """Check if command is in the blocked list."""
        cmd_lower = command.lower().strip()
        for blocked in self._blocked_commands:
            if blocked.lower() in cmd_lower:
                return True
        return False

    def _is_safe(self, command: str) -> bool:
        """Check if command is in the safe list."""
        cmd_parts = command.strip().split()
        if not cmd_parts:
            return False
        base_cmd = cmd_parts[0].lower()
        return base_cmd in [s.lower() for s in self._safe_commands]

    def _matches_dangerous_pattern(self, command: str) -> Optional[str]:
        """Check command against dangerous regex patterns."""
        for pattern in self._dangerous_re:
            if pattern.search(command):
                return pattern.pattern
        return None

    def _matches_safe_pattern(self, command: str) -> bool:
        """Check command against safe regex patterns."""
        for pattern in self._safe_re:
            if pattern.search(command):
                return True
        return False

    def _log_check(self, command: str, result: PermissionResult) -> None:
        """Log a permission check to audit log."""
        from datetime import datetime, timezone

        entry = {
            "command": command[:100],
            "level": result.level.value,
            "allowed": result.allowed,
            "reason": result.reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._audit_log.append(entry)

        # Keep last 200 entries
        if len(self._audit_log) > 200:
            self._audit_log = self._audit_log[-200:]

        if not result.allowed:
            logger.warning(
                f"BLOCKED: '{command[:50]}' — {result.reason}"
            )
        elif result.requires_confirmation:
            logger.info(
                f"CONFIRM: '{command[:50]}' — requires user approval"
            )
        else:
            logger.debug(f"SAFE: '{command[:50]}'")
