"""
JARVIS AI — Desktop Automation Module (Phase 3)

Keyboard and mouse control for desktop automation.
Uses subprocess-based xdotool (Linux) / PowerShell (Windows)
to avoid heavy pyautogui dependency.

Usage:
    from modules.automation.desktop_automation import register_automation_tools
    register_automation_tools(registry)
"""

from __future__ import annotations

import asyncio
import platform
import shutil
import time
from typing import Optional

from loguru import logger


SYSTEM = platform.system().lower()


def register_automation_tools(registry) -> None:
    """Register desktop automation tools."""

    # ═════════════════════════════════════════════════════════
    #  Type Text
    # ═════════════════════════════════════════════════════════

    @registry.register(
        name="type_text",
        description="Type text using keyboard simulation",
        category="automation",
        risk_level="confirm",
        examples=["Type 'Hello World'"],
    )
    async def type_text(text: str, delay_ms: int = 50) -> dict:
        """Simulate typing text character by character."""
        try:
            if SYSTEM == "linux":
                if shutil.which("xdotool"):
                    # xdotool handles special chars better with --delay
                    proc = await asyncio.create_subprocess_exec(
                        "xdotool", "type", "--delay", str(delay_ms), text,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    await proc.wait()
                    return {
                        "status": "typed",
                        "text": text[:100],
                        "length": len(text),
                        "tool": "xdotool",
                    }
                return {"status": "error", "error": "xdotool not found. Install: sudo apt install xdotool"}

            elif SYSTEM == "windows":
                # Use PowerShell SendKeys
                escaped = text.replace("'", "''")
                ps = f"""
                Add-Type -AssemblyName System.Windows.Forms
                [System.Windows.Forms.SendKeys]::SendWait('{escaped}')
                """
                proc = await asyncio.create_subprocess_exec(
                    "powershell", "-Command", ps,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await proc.wait()
                return {"status": "typed", "text": text[:100], "length": len(text)}

            return {"status": "error", "error": f"Unsupported platform: {SYSTEM}"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ═════════════════════════════════════════════════════════
    #  Press Key / Hotkey
    # ═════════════════════════════════════════════════════════

    @registry.register(
        name="press_key",
        description="Press a keyboard key or key combination",
        category="automation",
        risk_level="confirm",
        examples=[
            "Press Enter", "Press Ctrl+C",
            "Press Alt+Tab", "Press Ctrl+Alt+T",
        ],
    )
    async def press_key(key: str) -> dict:
        """
        Press a key or key combination.

        Supports: 'Enter', 'Escape', 'Tab', 'Space', 'Backspace',
                  'Ctrl+C', 'Ctrl+V', 'Alt+Tab', 'Ctrl+Alt+T', etc.
        """
        try:
            if SYSTEM == "linux":
                if not shutil.which("xdotool"):
                    return {"status": "error", "error": "xdotool not found"}

                # Convert common key names to xdotool format
                key_map = {
                    "enter": "Return", "return": "Return",
                    "escape": "Escape", "esc": "Escape",
                    "tab": "Tab", "space": "space",
                    "backspace": "BackSpace", "delete": "Delete",
                    "up": "Up", "down": "Down",
                    "left": "Left", "right": "Right",
                    "home": "Home", "end": "End",
                    "pageup": "Page_Up", "pagedown": "Page_Down",
                    "f1": "F1", "f2": "F2", "f3": "F3", "f4": "F4",
                    "f5": "F5", "f6": "F6", "f7": "F7", "f8": "F8",
                    "f9": "F9", "f10": "F10", "f11": "F11", "f12": "F12",
                    "printscreen": "Print", "pause": "Pause",
                }

                parts = [p.strip() for p in key.split("+")]
                xdotool_keys = []

                for part in parts:
                    lower = part.lower()
                    if lower in ("ctrl", "control"):
                        xdotool_keys.append("ctrl")
                    elif lower in ("alt",):
                        xdotool_keys.append("alt")
                    elif lower in ("shift",):
                        xdotool_keys.append("shift")
                    elif lower in ("super", "win", "meta", "windows"):
                        xdotool_keys.append("super")
                    elif lower in key_map:
                        xdotool_keys.append(key_map[lower])
                    else:
                        xdotool_keys.append(part)

                key_combo = "+".join(xdotool_keys)
                proc = await asyncio.create_subprocess_exec(
                    "xdotool", "key", key_combo,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await proc.communicate()

                if proc.returncode == 0:
                    return {"status": "pressed", "key": key, "xdotool_key": key_combo}
                else:
                    return {
                        "status": "error",
                        "key": key,
                        "error": stderr.decode("utf-8", errors="replace"),
                    }

            elif SYSTEM == "windows":
                # Map to PowerShell SendKeys format
                win_map = {
                    "enter": "{ENTER}", "escape": "{ESC}", "tab": "{TAB}",
                    "backspace": "{BACKSPACE}", "delete": "{DELETE}",
                    "up": "{UP}", "down": "{DOWN}", "left": "{LEFT}", "right": "{RIGHT}",
                }

                lower = key.lower()
                if lower in win_map:
                    ps_key = win_map[lower]
                elif "+" in key:
                    # Convert combo: Ctrl+C → ^(c)
                    parts = [p.strip().lower() for p in key.split("+")]
                    prefix = ""
                    actual = parts[-1]
                    for mod in parts[:-1]:
                        if mod in ("ctrl", "control"):
                            prefix += "^"
                        elif mod == "alt":
                            prefix += "%"
                        elif mod == "shift":
                            prefix += "+"
                    ps_key = f"{prefix}({actual})"
                else:
                    ps_key = key

                ps = f"""
                Add-Type -AssemblyName System.Windows.Forms
                [System.Windows.Forms.SendKeys]::SendWait('{ps_key}')
                """
                proc = await asyncio.create_subprocess_exec(
                    "powershell", "-Command", ps,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await proc.wait()
                return {"status": "pressed", "key": key}

            return {"status": "error", "error": f"Unsupported platform: {SYSTEM}"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ═════════════════════════════════════════════════════════
    #  Get Active Window
    # ═════════════════════════════════════════════════════════

    @registry.register(
        name="active_window",
        description="Get information about the currently active window",
        category="automation",
        risk_level="safe",
        examples=["What window is focused?", "Active window info"],
    )
    async def active_window() -> dict:
        """Get the currently focused window's name and process."""
        try:
            if SYSTEM == "linux":
                if shutil.which("xdotool"):
                    # Get active window ID
                    proc = await asyncio.create_subprocess_exec(
                        "xdotool", "getactivewindow", "getwindowname",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    stdout, _ = await proc.communicate()
                    window_name = stdout.decode("utf-8", errors="replace").strip()

                    # Get PID
                    proc2 = await asyncio.create_subprocess_exec(
                        "xdotool", "getactivewindow", "getwindowpid",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    stdout2, _ = await proc2.communicate()
                    pid_str = stdout2.decode("utf-8", errors="replace").strip()

                    result = {
                        "status": "ok",
                        "window_name": window_name,
                    }
                    if pid_str.isdigit():
                        result["pid"] = int(pid_str)
                        try:
                            p = psutil.Process(int(pid_str))
                            result["process_name"] = p.name()
                        except Exception:
                            pass

                    return result

                return {"status": "error", "error": "xdotool not found"}

            elif SYSTEM == "windows":
                ps = '''
                Add-Type @"
                    using System;
                    using System.Runtime.InteropServices;
                    using System.Text;
                    public class WinAPI {
                        [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
                        [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
                        [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
                    }
"@
                $handle = [WinAPI]::GetForegroundWindow()
                $sb = New-Object System.Text.StringBuilder 256
                [WinAPI]::GetWindowText($handle, $sb, 256) | Out-Null
                $pid = 0
                [WinAPI]::GetWindowThreadProcessId($handle, [ref]$pid) | Out-Null
                $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
                @{Title=$sb.ToString(); PID=$pid; Process=$proc.ProcessName} | ConvertTo-Json
                '''
                proc = await asyncio.create_subprocess_exec(
                    "powershell", "-Command", ps,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                stdout, _ = await proc.communicate()
                import json
                data = json.loads(stdout.decode("utf-8", errors="replace"))
                return {
                    "status": "ok",
                    "window_name": data.get("Title", ""),
                    "pid": data.get("PID", 0),
                    "process_name": data.get("Process", ""),
                }

            return {"status": "error", "error": f"Unsupported platform: {SYSTEM}"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ═════════════════════════════════════════════════════════
    #  Focus / Switch Window
    # ═════════════════════════════════════════════════════════

    @registry.register(
        name="focus_window",
        description="Focus a window by name or title",
        category="automation",
        risk_level="safe",
        examples=["Focus Firefox", "Switch to Terminal"],
    )
    async def focus_window(window_name: str) -> dict:
        """Bring a window to the foreground by its title."""
        try:
            if SYSTEM == "linux":
                if not shutil.which("xdotool"):
                    return {"status": "error", "error": "xdotool not found"}

                proc = await asyncio.create_subprocess_exec(
                    "xdotool", "search", "--name", window_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                stdout, _ = await proc.communicate()
                window_ids = stdout.decode("utf-8").strip().split("\n")

                if window_ids and window_ids[0]:
                    wid = window_ids[0]
                    await asyncio.create_subprocess_exec(
                        "xdotool", "windowactivate", wid,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    return {
                        "status": "focused",
                        "window": window_name,
                        "window_id": wid,
                    }

                return {
                    "status": "not_found",
                    "window": window_name,
                    "error": f"No window matching '{window_name}' found",
                }

            return {"status": "error", "error": f"Unsupported platform: {SYSTEM}"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ═════════════════════════════════════════════════════════
    #  Notification
    # ═════════════════════════════════════════════════════════

    @registry.register(
        name="notify",
        description="Send a desktop notification",
        category="automation",
        risk_level="safe",
        examples=["Send notification 'Scan complete'"],
    )
    async def notify(
        title: str = "JARVIS",
        message: str = "",
        urgency: str = "normal",
    ) -> dict:
        """Send a desktop notification."""
        try:
            if SYSTEM == "linux":
                if shutil.which("notify-send"):
                    cmd = [
                        "notify-send",
                        "--urgency", urgency,
                        "--icon", "dialog-information",
                        title,
                        message,
                    ]
                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    await proc.wait()
                    return {"status": "sent", "title": title, "message": message}

                return {"status": "error", "error": "notify-send not found"}

            elif SYSTEM == "windows":
                ps = f"""
                [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
                $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
                $textNodes = $template.GetElementsByTagName("text")
                $textNodes.Item(0).AppendChild($template.CreateTextNode("{title}")) | Out-Null
                $textNodes.Item(1).AppendChild($template.CreateTextNode("{message}")) | Out-Null
                $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
                [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("JARVIS").Show($toast)
                """
                proc = await asyncio.create_subprocess_exec(
                    "powershell", "-Command", ps,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await proc.wait()
                return {"status": "sent", "title": title, "message": message}

            return {"status": "error", "error": f"Unsupported platform: {SYSTEM}"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    logger.info(f"Registered automation tools (total: {registry.count})")


# Need psutil for active_window PID lookup
try:
    import psutil
except ImportError:
    psutil = None
