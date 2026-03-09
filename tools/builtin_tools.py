"""
JARVIS AI — Built-in Tools

Phase 1 built-in tools that are always available:
- System info & status
- Help & version
- Basic process listing

These serve as working examples for the tool registry pattern
and provide immediate utility.
"""

from __future__ import annotations

import platform
import shutil
from datetime import datetime, timezone

import psutil
from loguru import logger


def register_builtin_tools(registry) -> None:
    """Register all built-in tools with the provided ToolRegistry."""

    # ── System Info ───────────────────────────────────────

    @registry.register(
        name="system_info",
        description="Get current system information (OS, CPU, RAM, disk)",
        category="system",
        risk_level="safe",
        examples=["What's my system info?", "Show system status"],
    )
    async def system_info() -> dict:
        """Return comprehensive system information."""
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        cpu_freq = psutil.cpu_freq()

        return {
            "os": f"{platform.system()} {platform.release()}",
            "hostname": platform.node(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
            "cpu": {
                "cores_physical": psutil.cpu_count(logical=False),
                "cores_logical": psutil.cpu_count(logical=True),
                "frequency_mhz": round(cpu_freq.current, 0) if cpu_freq else "N/A",
                "usage_percent": psutil.cpu_percent(interval=0.5),
            },
            "memory": {
                "total_gb": round(mem.total / (1024 ** 3), 2),
                "used_gb": round(mem.used / (1024 ** 3), 2),
                "available_gb": round(mem.available / (1024 ** 3), 2),
                "percent": mem.percent,
            },
            "disk": {
                "total_gb": round(disk.total / (1024 ** 3), 2),
                "used_gb": round(disk.used / (1024 ** 3), 2),
                "free_gb": round(disk.free / (1024 ** 3), 2),
                "percent": disk.percent,
            },
        }

    # ── Process List ──────────────────────────────────────

    @registry.register(
        name="list_processes",
        description="List running processes, optionally filtered by name",
        category="system",
        risk_level="safe",
        examples=["What processes are running?", "Show running apps"],
    )
    async def list_processes(filter_name: str = "") -> list[dict]:
        """List running processes with resource usage."""
        processes = []
        for proc in psutil.process_iter(
            ["pid", "name", "cpu_percent", "memory_percent", "status"]
        ):
            try:
                info = proc.info
                if filter_name and filter_name.lower() not in info["name"].lower():
                    continue
                processes.append({
                    "pid": info["pid"],
                    "name": info["name"],
                    "cpu_percent": round(info["cpu_percent"] or 0, 1),
                    "memory_percent": round(info["memory_percent"] or 0, 1),
                    "status": info["status"],
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Sort by CPU usage descending, take top 20
        processes.sort(key=lambda p: p["cpu_percent"], reverse=True)
        return processes[:20]

    # ── Current Time ──────────────────────────────────────

    @registry.register(
        name="current_time",
        description="Get the current date and time",
        category="info",
        risk_level="safe",
        examples=["What time is it?", "Today's date"],
    )
    async def current_time() -> str:
        """Return current date and time."""
        now = datetime.now()
        utc_now = datetime.now(timezone.utc)
        return (
            f"Local: {now.strftime('%A, %B %d, %Y at %I:%M:%S %p')}\n"
            f"UTC:   {utc_now.strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )

    # ── Disk Space ────────────────────────────────────────

    @registry.register(
        name="disk_space",
        description="Check disk space usage for all partitions",
        category="system",
        risk_level="safe",
        examples=["How much disk space do I have?", "Check storage"],
    )
    async def disk_space() -> list[dict]:
        """Return disk usage for all mounted partitions."""
        partitions = []
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                partitions.append({
                    "device": part.device,
                    "mountpoint": part.mountpoint,
                    "filesystem": part.fstype,
                    "total_gb": round(usage.total / (1024 ** 3), 2),
                    "used_gb": round(usage.used / (1024 ** 3), 2),
                    "free_gb": round(usage.free / (1024 ** 3), 2),
                    "percent": usage.percent,
                })
            except (PermissionError, OSError):
                continue
        return partitions

    # ── Network Info ──────────────────────────────────────

    @registry.register(
        name="network_info",
        description="Get network interface information",
        category="system",
        risk_level="safe",
        examples=["Show my IP address", "Network status"],
    )
    async def network_info() -> dict:
        """Return network interface addresses and stats."""
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()

        interfaces = {}
        for name, addr_list in addrs.items():
            iface = {"addresses": [], "is_up": False}
            if name in stats:
                iface["is_up"] = stats[name].isup
                iface["speed_mbps"] = stats[name].speed

            for addr in addr_list:
                if addr.family.name in ("AF_INET", "AF_INET6"):
                    iface["addresses"].append({
                        "family": addr.family.name,
                        "address": addr.address,
                        "netmask": addr.netmask,
                    })
            if iface["addresses"]:  # Only include interfaces with IP addrs
                interfaces[name] = iface

        return interfaces

    # ── Battery Info ──────────────────────────────────────

    @registry.register(
        name="battery_info",
        description="Get battery status (laptops only)",
        category="system",
        risk_level="safe",
        examples=["Battery level?", "Am I plugged in?"],
    )
    async def battery_info() -> dict:
        """Return battery status."""
        battery = psutil.sensors_battery()
        if battery is None:
            return {"status": "No battery detected (desktop system)"}
        return {
            "percent": battery.percent,
            "plugged_in": battery.power_plugged,
            "time_left_minutes": (
                round(battery.secsleft / 60)
                if battery.secsleft > 0 else "Charging"
            ),
        }

    # ── Uptime ────────────────────────────────────────────

    @registry.register(
        name="system_uptime",
        description="Get system uptime",
        category="system",
        risk_level="safe",
        examples=["How long has the system been running?"],
    )
    async def system_uptime() -> str:
        """Return system uptime."""
        import time
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time
        days = uptime.days
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        return (
            f"Booted: {boot_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Uptime: {days}d {hours}h {minutes}m"
        )

    logger.info(f"Registered {registry.count} built-in tools")
