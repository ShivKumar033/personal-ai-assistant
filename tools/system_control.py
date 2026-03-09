"""
JARVIS AI — System Control Tools (Phase 3)

Cross-platform tools for controlling the operating system:
- Open / close applications
- Volume & brightness control
- System power actions
- Clipboard management
- Shell command execution

Usage:
    from tools.system_control import register_system_tools
    register_system_tools(registry)
"""

from __future__ import annotations

import asyncio
import os
import platform
import shlex
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Optional

import psutil
from loguru import logger


SYSTEM = platform.system().lower()


def register_system_tools(registry) -> None:
    """Register OS-control tools with the provided ToolRegistry."""

    # ═════════════════════════════════════════════════════════
    #  Open Application
    # ═════════════════════════════════════════════════════════

    @registry.register(
        name="open_app",
        description="Open an application by name",
        category="system",
        risk_level="safe",
        examples=["Open Firefox", "Launch terminal", "Start BurpSuite"],
    )
    async def open_app(app_name: str) -> dict:
        """
        Open an application by name.

        Uses xdg-open / open / os.startfile depending on platform.
        Searches common application paths and tries multiple strategies.
        """
        app = app_name.strip().lower()
        logger.info(f"Opening application: {app_name}")

        # ── Strategy 1: Direct executable lookup ──────
        exe_path = shutil.which(app)
        if exe_path:
            proc = await asyncio.create_subprocess_exec(
                exe_path,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            return {
                "status": "opened",
                "app": app_name,
                "pid": proc.pid,
                "method": "direct",
            }

        # ── Strategy 2: Common name mappings ──────────
        app_aliases = {
            "firefox": ["firefox", "firefox-esr"],
            "chrome": ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"],
            "terminal": ["gnome-terminal", "xfce4-terminal", "konsole", "xterm", "kitty", "alacritty"],
            "files": ["nautilus", "thunar", "dolphin", "nemo", "pcmanfm"],
            "text editor": ["gedit", "kate", "mousepad", "xed", "nano"],
            "code": ["code", "codium"],
            "vscode": ["code", "codium"],
            "burpsuite": ["burpsuite", "BurpSuiteCommunity", "BurpSuitePro"],
            "wireshark": ["wireshark"],
            "nmap": ["nmap", "zenmap"],
            "calculator": ["gnome-calculator", "kcalc", "galculator"],
            "music": ["rhythmbox", "vlc", "audacious"],
            "video": ["vlc", "totem", "mpv"],
            "screenshot": ["gnome-screenshot", "flameshot", "spectacle"],
            "settings": ["gnome-control-center", "xfce4-settings-manager"],
        }

        candidates = app_aliases.get(app, [app])

        for candidate in candidates:
            exe = shutil.which(candidate)
            if exe:
                proc = await asyncio.create_subprocess_exec(
                    exe,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                return {
                    "status": "opened",
                    "app": candidate,
                    "pid": proc.pid,
                    "method": "alias",
                }

        # ── Strategy 3: Desktop file search (Linux) ───
        if SYSTEM == "linux":
            desktop_dirs = [
                Path("/usr/share/applications"),
                Path("/usr/local/share/applications"),
                Path.home() / ".local/share/applications",
            ]
            for ddir in desktop_dirs:
                if not ddir.exists():
                    continue
                for desktop_file in ddir.glob("*.desktop"):
                    try:
                        content = desktop_file.read_text(errors="ignore").lower()
                        if app in content:
                            proc = await asyncio.create_subprocess_exec(
                                "xdg-open", str(desktop_file),
                                stdout=asyncio.subprocess.DEVNULL,
                                stderr=asyncio.subprocess.DEVNULL,
                            )
                            return {
                                "status": "opened",
                                "app": desktop_file.stem,
                                "pid": proc.pid,
                                "method": "desktop_file",
                            }
                    except Exception:
                        continue

        return {
            "status": "not_found",
            "app": app_name,
            "error": f"Could not find application '{app_name}'. "
                     f"Make sure it's installed and in your PATH.",
        }

    # ═════════════════════════════════════════════════════════
    #  Close Application
    # ═════════════════════════════════════════════════════════

    @registry.register(
        name="close_app",
        description="Close a running application by name",
        category="system",
        risk_level="confirm",
        examples=["Close Firefox", "Kill terminal"],
    )
    async def close_app(app_name: str) -> dict:
        """Close an application by terminating its process(es)."""
        app = app_name.strip().lower()
        killed = []
        not_found = True

        for proc in psutil.process_iter(["pid", "name"]):
            try:
                if app in proc.info["name"].lower():
                    not_found = False
                    proc.terminate()
                    killed.append({
                        "pid": proc.info["pid"],
                        "name": proc.info["name"],
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if not_found:
            return {
                "status": "not_found",
                "app": app_name,
                "error": f"No running process matching '{app_name}' found.",
            }

        # Give processes time to gracefully exit
        await asyncio.sleep(1.0)

        # Force kill any remainders
        for proc_info in killed:
            try:
                p = psutil.Process(proc_info["pid"])
                if p.is_running():
                    p.kill()
                    proc_info["force_killed"] = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        return {
            "status": "closed",
            "app": app_name,
            "processes_terminated": len(killed),
            "details": killed,
        }

    # ═════════════════════════════════════════════════════════
    #  Run Shell Command
    # ═════════════════════════════════════════════════════════

    @registry.register(
        name="run_shell",
        description="Execute a shell command and return the output",
        category="system",
        risk_level="confirm",
        examples=["Run 'ls -la'", "Execute 'df -h'"],
    )
    async def run_shell(
        command: str,
        timeout: int = 30,
        cwd: str = "",
    ) -> dict:
        """
        Execute a shell command with security checks.

        Returns stdout, stderr, and return code.
        Has a timeout to prevent hanging commands.
        """
        logger.info(f"Executing shell command: {command}")

        working_dir = cwd if cwd else str(Path.home())

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                proc.kill()
                return {
                    "status": "timeout",
                    "command": command,
                    "timeout_seconds": timeout,
                    "error": f"Command timed out after {timeout}s",
                }

            stdout_text = stdout.decode("utf-8", errors="replace").strip()
            stderr_text = stderr.decode("utf-8", errors="replace").strip()

            return {
                "status": "completed",
                "command": command,
                "return_code": proc.returncode,
                "stdout": stdout_text[:5000],   # Cap output
                "stderr": stderr_text[:2000],
                "success": proc.returncode == 0,
            }

        except Exception as e:
            return {
                "status": "error",
                "command": command,
                "error": str(e),
            }

    # ═════════════════════════════════════════════════════════
    #  Kill Process by PID
    # ═════════════════════════════════════════════════════════

    @registry.register(
        name="kill_process",
        description="Kill a process by its PID",
        category="system",
        risk_level="confirm",
        examples=["Kill process 12345"],
    )
    async def kill_process(pid: int, force: bool = False) -> dict:
        """Kill a process by PID. Use force=True for SIGKILL."""
        try:
            proc = psutil.Process(pid)
            name = proc.name()

            if force:
                proc.kill()
                method = "SIGKILL"
            else:
                proc.terminate()
                method = "SIGTERM"

            return {
                "status": "killed",
                "pid": pid,
                "name": name,
                "method": method,
            }
        except psutil.NoSuchProcess:
            return {"status": "not_found", "pid": pid, "error": "Process not found"}
        except psutil.AccessDenied:
            return {"status": "denied", "pid": pid, "error": "Access denied — try with sudo"}

    # ═════════════════════════════════════════════════════════
    #  Clipboard
    # ═════════════════════════════════════════════════════════

    @registry.register(
        name="clipboard_copy",
        description="Copy text to the system clipboard",
        category="system",
        risk_level="safe",
        examples=["Copy this to clipboard"],
    )
    async def clipboard_copy(text: str) -> dict:
        """Copy text to the system clipboard."""
        try:
            if SYSTEM == "linux":
                # Try xclip first, then xsel
                for tool in ["xclip", "xsel"]:
                    if shutil.which(tool):
                        if tool == "xclip":
                            cmd = ["xclip", "-selection", "clipboard"]
                        else:
                            cmd = ["xsel", "--clipboard", "--input"]
                        proc = await asyncio.create_subprocess_exec(
                            *cmd,
                            stdin=asyncio.subprocess.PIPE,
                        )
                        await proc.communicate(input=text.encode("utf-8"))
                        return {"status": "copied", "length": len(text), "tool": tool}

                return {"status": "error", "error": "Install xclip or xsel for clipboard support"}

            elif SYSTEM == "windows":
                proc = await asyncio.create_subprocess_exec(
                    "clip",
                    stdin=asyncio.subprocess.PIPE,
                )
                await proc.communicate(input=text.encode("utf-8"))
                return {"status": "copied", "length": len(text), "tool": "clip"}

            return {"status": "error", "error": f"Unsupported platform: {SYSTEM}"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    @registry.register(
        name="clipboard_paste",
        description="Get text from the system clipboard",
        category="system",
        risk_level="safe",
        examples=["What's in my clipboard?"],
    )
    async def clipboard_paste() -> dict:
        """Get text from the system clipboard."""
        try:
            if SYSTEM == "linux":
                for tool in ["xclip", "xsel"]:
                    if shutil.which(tool):
                        if tool == "xclip":
                            cmd = ["xclip", "-selection", "clipboard", "-o"]
                        else:
                            cmd = ["xsel", "--clipboard", "--output"]
                        proc = await asyncio.create_subprocess_exec(
                            *cmd,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )
                        stdout, _ = await proc.communicate()
                        return {
                            "status": "ok",
                            "content": stdout.decode("utf-8", errors="replace"),
                        }

                return {"status": "error", "error": "Install xclip or xsel"}

            elif SYSTEM == "windows":
                proc = await asyncio.create_subprocess_exec(
                    "powershell", "-command", "Get-Clipboard",
                    stdout=asyncio.subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()
                return {
                    "status": "ok",
                    "content": stdout.decode("utf-8", errors="replace"),
                }

            return {"status": "error", "error": f"Unsupported platform: {SYSTEM}"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ═════════════════════════════════════════════════════════
    #  Open URL
    # ═════════════════════════════════════════════════════════

    @registry.register(
        name="open_url",
        description="Open a URL in the default web browser",
        category="web",
        risk_level="safe",
        examples=["Open google.com", "Browse to github.com"],
    )
    async def open_url(url: str) -> dict:
        """Open a URL in the system's default web browser."""
        import webbrowser

        # Ensure URL has a scheme
        if not url.startswith(("http://", "https://", "file://")):
            url = "https://" + url

        try:
            webbrowser.open(url)
            return {"status": "opened", "url": url}
        except Exception as e:
            return {"status": "error", "url": url, "error": str(e)}

    # ═════════════════════════════════════════════════════════
    #  System Power Actions
    # ═════════════════════════════════════════════════════════

    @registry.register(
        name="lock_screen",
        description="Lock the computer screen",
        category="system",
        risk_level="confirm",
        examples=["Lock my screen", "Lock the computer"],
    )
    async def lock_screen() -> dict:
        """Lock the computer screen."""
        try:
            if SYSTEM == "linux":
                # Try different lock commands
                for cmd in [
                    ["loginctl", "lock-session"],
                    ["xdg-screensaver", "lock"],
                    ["gnome-screensaver-command", "-l"],
                    ["xscreensaver-command", "-lock"],
                ]:
                    if shutil.which(cmd[0]):
                        await asyncio.create_subprocess_exec(
                            *cmd,
                            stdout=asyncio.subprocess.DEVNULL,
                            stderr=asyncio.subprocess.DEVNULL,
                        )
                        return {"status": "locked", "method": cmd[0]}

                return {"status": "error", "error": "No screen locker found"}

            elif SYSTEM == "windows":
                await asyncio.create_subprocess_exec(
                    "rundll32.exe", "user32.dll,LockWorkStation",
                )
                return {"status": "locked", "method": "LockWorkStation"}

            return {"status": "error", "error": f"Unsupported platform: {SYSTEM}"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ═════════════════════════════════════════════════════════
    #  Screenshot
    # ═════════════════════════════════════════════════════════

    @registry.register(
        name="take_screenshot",
        description="Take a screenshot and save it to a file",
        category="system",
        risk_level="safe",
        examples=["Take a screenshot", "Capture my screen"],
    )
    async def take_screenshot(output_path: str = "") -> dict:
        """Take a screenshot and save to file."""
        from datetime import datetime as dt

        if not output_path:
            timestamp = dt.now().strftime("%Y%m%d_%H%M%S")
            output_path = str(
                Path.home() / "Pictures" / f"jarvis_screenshot_{timestamp}.png"
            )

        # Ensure output directory exists
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        try:
            if SYSTEM == "linux":
                # Try multiple screenshot tools
                tools = [
                    (["gnome-screenshot", "-f", output_path], "gnome-screenshot"),
                    (["scrot", output_path], "scrot"),
                    (["import", "-window", "root", output_path], "imagemagick"),
                    (["flameshot", "full", "-p", str(Path(output_path).parent)], "flameshot"),
                ]
                for cmd, name in tools:
                    if shutil.which(cmd[0]):
                        proc = await asyncio.create_subprocess_exec(
                            *cmd,
                            stdout=asyncio.subprocess.DEVNULL,
                            stderr=asyncio.subprocess.DEVNULL,
                        )
                        await proc.wait()
                        if proc.returncode == 0 or Path(output_path).exists():
                            return {
                                "status": "captured",
                                "path": output_path,
                                "tool": name,
                            }

                return {"status": "error", "error": "No screenshot tool found (install scrot or gnome-screenshot)"}

            elif SYSTEM == "windows":
                # Use PowerShell for screenshots
                ps_script = f'''
                Add-Type -AssemblyName System.Windows.Forms
                $screen = [System.Windows.Forms.Screen]::PrimaryScreen
                $bitmap = New-Object System.Drawing.Bitmap($screen.Bounds.Width, $screen.Bounds.Height)
                $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
                $graphics.CopyFromScreen($screen.Bounds.Location, [System.Drawing.Point]::Empty, $screen.Bounds.Size)
                $bitmap.Save("{output_path}")
                '''
                proc = await asyncio.create_subprocess_exec(
                    "powershell", "-Command", ps_script,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await proc.wait()
                return {
                    "status": "captured",
                    "path": output_path,
                    "tool": "powershell",
                }

            return {"status": "error", "error": f"Unsupported platform: {SYSTEM}"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    logger.info(f"Registered system control tools (total: {registry.count})")
