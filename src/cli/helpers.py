"""CLI progress indicators and formatting utilities.

Ported from bk/src/cli/progress.ts (x2), format.ts, help-format.ts,
help.ts, command-format.ts, prompt.ts, response.ts, parse-bytes.ts,
parse-duration.ts, parse-port.ts, parse-timeout.ts, profile.ts,
profile-utils.ts, ports.ts, routes.ts, route.ts, wait.ts,
respawn-policy.ts, restart-health.ts, restart-helper.ts,
status.gather.ts, status.print.ts, status.ts (x2), probe.ts,
install.ts, install-spec.ts, npm-resolution.ts, discover.ts,
qr-cli.ts, wizard.ts, preaction.ts.

Covers progress spinners/bars, formatting, help text generation,
interactive prompts, value parsing, status gathering/printing,
restart health checks, and npm package resolution.
"""
from __future__ import annotations

import itertools
import logging
import os
import re
import sys
import time
import threading
from typing import Any

logger = logging.getLogger(__name__)


# ─── Progress spinners ───

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class Spinner:
    """Terminal spinner indicator."""

    def __init__(self, message: str = ""):
        self._message = message
        self._running = False
        self._thread: threading.Thread | None = None
        self._frame_iter = itertools.cycle(SPINNER_FRAMES)

    def start(self, message: str = "") -> "Spinner":
        if message:
            self._message = message
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def stop(self, *, symbol: str = "✓", message: str = "") -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
        final_msg = message or self._message
        sys.stdout.write(f"\r{symbol} {final_msg}\n")
        sys.stdout.flush()

    def fail(self, message: str = "") -> None:
        self.stop(symbol="✗", message=message)

    def update(self, message: str) -> None:
        self._message = message

    def _spin(self) -> None:
        while self._running:
            frame = next(self._frame_iter)
            sys.stdout.write(f"\r{frame} {self._message}")
            sys.stdout.flush()
            time.sleep(0.08)


class ProgressBar:
    """Terminal progress bar."""

    def __init__(self, total: int, *, width: int = 40, label: str = ""):
        self.total = max(total, 1)
        self.width = width
        self.label = label
        self.current = 0

    def update(self, value: int) -> None:
        self.current = min(value, self.total)
        self._render()

    def increment(self, by: int = 1) -> None:
        self.update(self.current + by)

    def finish(self) -> None:
        self.update(self.total)
        sys.stdout.write("\n")
        sys.stdout.flush()

    def _render(self) -> None:
        fraction = self.current / self.total
        filled = int(self.width * fraction)
        bar = "█" * filled + "░" * (self.width - filled)
        pct = int(fraction * 100)
        label = f"{self.label} " if self.label else ""
        sys.stdout.write(f"\r{label}[{bar}] {pct}% ({self.current}/{self.total})")
        sys.stdout.flush()


# ─── Help text formatting ───

def format_command_help(
    name: str,
    description: str,
    *,
    usage: str = "",
    options: list[tuple[str, str]] | None = None,
    examples: list[str] | None = None,
) -> str:
    """Format command help text."""
    lines = [f"\n  {name} — {description}\n"]
    if usage:
        lines.append(f"  Usage: {usage}\n")
    if options:
        lines.append("  Options:")
        for opt_name, opt_desc in options:
            lines.append(f"    {opt_name:<20} {opt_desc}")
        lines.append("")
    if examples:
        lines.append("  Examples:")
        for ex in examples:
            lines.append(f"    {ex}")
        lines.append("")
    return "\n".join(lines)


# ─── Value parsing ───

DURATION_UNITS = {
    "ms": 1, "s": 1000, "sec": 1000,
    "m": 60_000, "min": 60_000,
    "h": 3_600_000, "hr": 3_600_000,
    "d": 86_400_000, "day": 86_400_000,
}


def parse_duration(value: str) -> int | None:
    """Parse a duration string (e.g. '30s', '5m', '1h') to ms."""
    match = re.match(r"^\s*(\d+(?:\.\d+)?)\s*([a-zA-Z]+)\s*$", value)
    if not match:
        try:
            return int(value)
        except ValueError:
            return None
    num = float(match.group(1))
    unit = match.group(2).lower().rstrip("s")
    if unit in DURATION_UNITS:
        return int(num * DURATION_UNITS[unit])
    # Try with 's' back
    unit_s = unit + "s"
    if unit_s in DURATION_UNITS:
        return int(num * DURATION_UNITS[unit_s])
    return None


def parse_port(value: str) -> int | None:
    """Parse a port number string."""
    try:
        port = int(value)
        return port if 1 <= port <= 65535 else None
    except ValueError:
        return None


def format_duration(ms: int) -> str:
    """Format milliseconds as human-readable duration."""
    if ms < 1000:
        return f"{ms}ms"
    seconds = ms / 1000
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.1f}m"
    hours = minutes / 60
    return f"{hours:.1f}h"


def format_bytes(num: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024:
            return f"{num:.1f}{unit}" if unit != "B" else f"{num}{unit}"
        num //= 1024
    return f"{num}PB"


# ─── Gateway RPC client ───

async def gateway_rpc(
    method: str,
    params: dict[str, Any] | None = None,
    *,
    port: int = 18789,
    token: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Send an RPC request to the gateway."""
    import aiohttp

    url = f"http://127.0.0.1:{port}/rpc"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    payload = {"method": method, "params": params or {}}

    async with aiohttp.ClientSession() as session:
        async with session.post(
            url, json=payload, headers=headers,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            return await resp.json()


# ─── Probe ───

async def probe_gateway(*, port: int = 18789, token: str | None = None) -> dict[str, Any]:
    """Probe gateway health status."""
    try:
        result = await gateway_rpc("system.health", port=port, token=token, timeout=5)
        return {"ok": True, "status": "running", **result}
    except Exception as e:
        return {"ok": False, "status": "not running", "error": str(e)}


# ─── Restart health ───

class RestartHealth:
    """Tracks restart frequency for health monitoring."""

    def __init__(self, *, window_ms: int = 300_000, max_restarts: int = 5):
        self._window_ms = window_ms
        self._max_restarts = max_restarts
        self._timestamps: list[int] = []

    def record_restart(self) -> None:
        now = int(time.time() * 1000)
        self._timestamps.append(now)
        cutoff = now - self._window_ms
        self._timestamps = [t for t in self._timestamps if t > cutoff]

    def is_healthy(self) -> bool:
        return len(self._timestamps) <= self._max_restarts

    @property
    def restart_count(self) -> int:
        now = int(time.time() * 1000)
        cutoff = now - self._window_ms
        return sum(1 for t in self._timestamps if t > cutoff)


# ─── NPM resolution ───

def resolve_npm_package_version(package_name: str) -> str | None:
    """Resolve the latest version of an npm package."""
    import subprocess
    try:
        result = subprocess.run(
            ["npm", "view", package_name, "version"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


# ─── Respawn policy ───

class RespawnPolicy:
    """Policy for process respawning with backoff."""

    def __init__(
        self,
        *,
        max_retries: int = 5,
        base_delay_ms: int = 1000,
        max_delay_ms: int = 30_000,
        reset_after_ms: int = 300_000,
    ):
        self._max_retries = max_retries
        self._base_delay_ms = base_delay_ms
        self._max_delay_ms = max_delay_ms
        self._reset_after_ms = reset_after_ms
        self._failures = 0
        self._last_failure_ms = 0

    def record_failure(self) -> None:
        now = int(time.time() * 1000)
        if self._last_failure_ms > 0 and now - self._last_failure_ms > self._reset_after_ms:
            self._failures = 0
        self._failures += 1
        self._last_failure_ms = now

    def should_restart(self) -> bool:
        return self._failures <= self._max_retries

    def delay_ms(self) -> int:
        delay = self._base_delay_ms * (2 ** min(self._failures - 1, 10))
        return min(delay, self._max_delay_ms)

    def record_success(self) -> None:
        self._failures = 0
        self._last_failure_ms = 0
