"""Infra ports — ported from bk/src/infra/ports.ts, ports-format.ts,
ports-inspect.ts, ports-lsof.ts, ports-probe.ts, ports-types.ts.

Port inspection, probing, formatting, lsof queries.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import socket
import subprocess
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("infra.ports")


# ─── ports-types.ts ───

@dataclass
class PortInfo:
    port: int = 0
    pid: int | None = None
    process_name: str | None = None
    protocol: str = "tcp"
    state: str = ""
    address: str = ""


# ─── ports-probe.ts ───

def probe_port(port: int, host: str = "127.0.0.1", timeout_s: float = 1.0) -> bool:
    """Probe if a port is accepting connections."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout_s)
            s.connect((host, port))
            return True
    except (OSError, ConnectionRefusedError):
        return False


async def probe_port_async(port: int, host: str = "127.0.0.1", timeout_s: float = 1.0) -> bool:
    """Async version of port probe."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, probe_port, port, host, timeout_s)


def probe_ports(ports: list[int], host: str = "127.0.0.1", timeout_s: float = 0.5) -> dict[int, bool]:
    """Probe multiple ports and return status dict."""
    return {port: probe_port(port, host, timeout_s) for port in ports}


# ─── ports-lsof.ts ───

def lsof_port(port: int) -> list[PortInfo]:
    """Query lsof for processes listening on a port."""
    results: list[PortInfo] = []
    try:
        output = subprocess.run(
            ["lsof", "-i", f":{port}", "-P", "-n"],
            capture_output=True, text=True, timeout=5.0,
        )
        for line in output.stdout.strip().split("\n")[1:]:  # skip header
            parts = line.split()
            if len(parts) < 9:
                continue
            process_name = parts[0]
            pid = int(parts[1]) if parts[1].isdigit() else None
            state = parts[-1] if parts[-1] in ("LISTEN", "ESTABLISHED", "CLOSE_WAIT", "TIME_WAIT") else ""
            results.append(PortInfo(
                port=port,
                pid=pid,
                process_name=process_name,
                state=state,
            ))
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return results


# ─── ports-inspect.ts ───

def inspect_port(port: int) -> PortInfo | None:
    """Get detailed info about what's listening on a port."""
    results = lsof_port(port)
    # Prefer LISTEN state
    for info in results:
        if info.state == "LISTEN":
            return info
    return results[0] if results else None


def inspect_ports(ports: list[int]) -> dict[int, PortInfo | None]:
    """Inspect multiple ports."""
    return {port: inspect_port(port) for port in ports}


def get_listening_ports() -> list[PortInfo]:
    """Get all listening TCP ports."""
    results: list[PortInfo] = []
    try:
        output = subprocess.run(
            ["lsof", "-i", "-P", "-n", "-sTCP:LISTEN"],
            capture_output=True, text=True, timeout=10.0,
        )
        for line in output.stdout.strip().split("\n")[1:]:
            parts = line.split()
            if len(parts) < 9:
                continue
            process_name = parts[0]
            pid = int(parts[1]) if parts[1].isdigit() else None
            # Extract port from address field
            addr_field = parts[8] if len(parts) > 8 else ""
            port_match = re.search(r":(\d+)$", addr_field)
            port = int(port_match.group(1)) if port_match else 0
            results.append(PortInfo(
                port=port,
                pid=pid,
                process_name=process_name,
                protocol="tcp",
                state="LISTEN",
                address=addr_field,
            ))
    except (subprocess.SubprocessError, FileNotFoundError):
        # Fallback: try ss on Linux
        try:
            output = subprocess.run(
                ["ss", "-tlnp"],
                capture_output=True, text=True, timeout=10.0,
            )
            for line in output.stdout.strip().split("\n")[1:]:
                parts = line.split()
                if len(parts) < 5:
                    continue
                addr = parts[3]
                port_match = re.search(r":(\d+)$", addr)
                port = int(port_match.group(1)) if port_match else 0
                # Extract PID from last field
                pid_match = re.search(r"pid=(\d+)", parts[-1]) if len(parts) > 5 else None
                pid = int(pid_match.group(1)) if pid_match else None
                name_match = re.search(r'"([^"]+)"', parts[-1]) if len(parts) > 5 else None
                results.append(PortInfo(
                    port=port,
                    pid=pid,
                    process_name=name_match.group(1) if name_match else None,
                    protocol="tcp",
                    state="LISTEN",
                    address=addr,
                ))
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
    return results


# ─── ports-format.ts ───

def format_port_info(info: PortInfo) -> str:
    """Format port info for display."""
    parts = [f":{info.port}"]
    if info.process_name:
        parts.append(f"({info.process_name})")
    if info.pid:
        parts.append(f"pid={info.pid}")
    if info.state:
        parts.append(f"[{info.state}]")
    return " ".join(parts)


def format_port_list(ports: list[PortInfo]) -> str:
    """Format a list of port infos."""
    if not ports:
        return "No ports in use"
    lines = [format_port_info(p) for p in sorted(ports, key=lambda p: p.port)]
    return "\n".join(lines)


def format_port_status(port: int, in_use: bool, info: PortInfo | None = None) -> str:
    """Format port status for display."""
    if not in_use:
        return f":{port} — available"
    if info:
        return f":{port} — in use by {info.process_name or 'unknown'} (pid={info.pid or '?'})"
    return f":{port} — in use"


# ─── ports.ts (main) ───

async def find_available_port(
    start: int = 3000,
    end: int = 9000,
    host: str = "127.0.0.1",
) -> int | None:
    """Find an available port in the given range."""
    for port in range(start, end):
        if not probe_port(port, host, timeout_s=0.1):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind((host, port))
                    return port
            except OSError:
                continue
    return None


def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a port is available for binding."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return True
    except OSError:
        return False
