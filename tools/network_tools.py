"""
JARVIS AI — Network Tools (Phase 6)

Advanced networking capabilities:
- IP address lookup (Internal & External)
- Network speed test
- Wi-Fi scanning (Linux)
- DNS lookup
"""

from __future__ import annotations

import asyncio
import platform
import shutil
import socket
import subprocess
from typing import Any

from loguru import logger
import httpx

SYSTEM = platform.system().lower()

def register_network_tools(registry) -> None:
    """Register all network-related tools."""

    @registry.register(
        name="get_ip_addresses",
        description="Get local and public IP addresses",
        category="network",
        risk_level="safe",
        examples=["What is my IP?", "Show my network addresses"],
    )
    async def get_ip_addresses() -> dict:
        """Fetch local and public IP info."""
        # Local IP
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        
        # Public IP (async)
        public_ip = "Unknown"
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get("https://api64.ipify.org?format=json")
                if resp.status_code == 200:
                    public_ip = resp.json().get("ip", "Unknown")
        except Exception:
            pass

        return {
            "hostname": hostname,
            "local_ip": local_ip,
            "public_ip": public_ip
        }

    @registry.register(
        name="scan_wifi",
        description="Scan for nearby Wi-Fi networks (Linux/Kali)",
        category="network",
        risk_level="safe",
        examples=["Scan for Wi-Fi", "What networks are nearby?"],
    )
    async def scan_wifi() -> dict:
        """Scan Wi-Fi using nmcli or iwlist."""
        if SYSTEM != "linux":
            return {"status": "error", "error": "Wi-Fi scanning only supported on Linux"}
        
        if shutil.which("nmcli"):
            cmd = ["nmcli", "-t", "-f", "SSID,SIGNAL,BARS,SECURITY", "dev", "wifi"]
            method = "nmcli"
        else:
            return {"status": "error", "error": "nmcli not found (install network-manager)"}

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            networks = stdout.decode().strip().split("\n")
            
            # Clean up
            results = []
            for n in networks:
                parts = n.split(":")
                if len(parts) >= 4:
                    results.append({
                        "ssid": parts[0],
                        "signal": parts[1],
                        "security": parts[3]
                    })
            
            return {"status": "ok", "method": method, "networks": results[:10]}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @registry.register(
        name="network_ping",
        description="Ping a host to check connectivity",
        category="network",
        risk_level="safe",
        examples=["Ping google.com", "Check my internet"],
    )
    async def network_ping(host: str = "8.8.8.8", count: int = 4) -> dict:
        """Ping a host."""
        cmd = ["ping", "-c" if SYSTEM != "windows" else "-n", str(count), host]
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            output = stdout.decode().strip()
            
            return {
                "status": "ok" if proc.returncode == 0 else "failed",
                "host": host,
                "output": output[-500:] # Last bits of ping
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    logger.info(f"Registered network tools (total: {registry.count})")
