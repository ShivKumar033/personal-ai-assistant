"""
JARVIS AI — Hardware Tools (Phase 6)

Advanced tools for monitoring and interacting with laptop hardware:
- Battery status
- Thermal sensors
- Advanced CPU/RAM metrics
- Disk health/space
"""

from __future__ import annotations

import asyncio
import platform
import shutil
from typing import Any

import psutil
from loguru import logger

SYSTEM = platform.system().lower()

def register_hardware_tools(registry) -> None:
    """Register all hardware-related tools."""

    @registry.register(
        name="get_battery_status",
        description="Check laptop battery percentage and charging status",
        category="hardware",
        risk_level="safe",
        examples=["How much battery is left?", "Is my laptop charging?"],
    )
    async def get_battery_status() -> dict:
        """Get battery stats using psutil."""
        battery = psutil.sensors_battery()
        if battery is None:
            return {"status": "error", "error": "No battery detected (desktop PC?)"}
        
        return {
            "percent": round(battery.percent, 1),
            "secs_left": battery.secsleft if battery.secsleft != -1 else "Calculating...",
            "power_plugged": battery.power_plugged,
            "status": "charging" if battery.power_plugged else "discharging"
        }

    @registry.register(
        name="get_system_temps",
        description="Check hardware temperatures (CPU, GPU, battery)",
        category="hardware",
        risk_level="safe",
        examples=["Is my laptop overheating?", "Check CPU temperature"],
    )
    async def get_system_temps() -> dict:
        """Get thermal sensor data."""
        if SYSTEM != "linux":
            return {"status": "error", "error": "Temperature sensors only supported on Linux via psutil"}
            
        temps = {}
        try:
            raw_temps = psutil.sensors_temperatures()
            for name, entries in raw_temps.items():
                temps[name] = [{"label": e.label or "core", "current": e.current, "high": e.high, "critical": e.critical} for e in entries]
            
            return {"status": "ok", "temperatures": temps}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @registry.register(
        name="get_detailed_resources",
        description="Get real-time CPU and Memory usage per core",
        category="hardware",
        risk_level="safe",
        examples=["Show me per-core CPU usage", "Detailed RAM status"],
    )
    async def get_detailed_resources() -> dict:
        """Detailed resource breakdown."""
        cpu_percent = psutil.cpu_percent(interval=None, percpu=True)
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        return {
            "cpu_cores": cpu_percent,
            "ram": {
                "total": mem.total,
                "percent": mem.percent,
                "cached": getattr(mem, "cached", 0),
                "buffers": getattr(mem, "buffers", 0),
            },
            "swap": {
                "total": swap.total,
                "percent": swap.percent
            }
        }

    logger.info(f"Registered hardware tools (total: {registry.count})")
