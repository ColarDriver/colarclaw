"""Process management utilities.

Ported from bk/src/process/ (~15 TS files).

Covers child process spawning, signal handling, PID management,
process health monitoring, graceful shutdown, and watchdog timers.
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "ProcessInfo", "spawn_process", "kill_process_tree",
    "is_port_in_use", "wait_for_port", "GracefulShutdown",
    "ProcessWatchdog",
]


@dataclass
class ProcessInfo:
    """Information about a spawned process."""
    pid: int = 0
    command: str = ""
    args: list[str] = field(default_factory=list)
    started_at_ms: int = 0
    exit_code: int | None = None


def spawn_process(
    command: str,
    args: list[str] | None = None,
    *,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    stdout_path: str | None = None,
    stderr_path: str | None = None,
    detach: bool = False,
) -> ProcessInfo:
    """Spawn a child process."""
    full_args = [command] + (args or [])
    kwargs: dict[str, Any] = {}

    if cwd:
        kwargs["cwd"] = cwd
    if env:
        full_env = {**os.environ, **env}
        kwargs["env"] = full_env
    if detach:
        kwargs["start_new_session"] = True

    stdout_f = open(stdout_path, "a") if stdout_path else subprocess.DEVNULL
    stderr_f = open(stderr_path, "a") if stderr_path else subprocess.DEVNULL

    proc = subprocess.Popen(
        full_args,
        stdout=stdout_f,
        stderr=stderr_f,
        **kwargs,
    )

    return ProcessInfo(
        pid=proc.pid,
        command=command,
        args=args or [],
        started_at_ms=int(time.time() * 1000),
    )


def kill_process_tree(pid: int, *, sig: int = signal.SIGTERM, timeout: float = 10.0) -> bool:
    """Kill a process and all its children."""
    try:
        # Try to kill children first (Linux)
        children = _get_child_pids(pid)
        for child_pid in children:
            try:
                os.kill(child_pid, sig)
            except ProcessLookupError:
                pass

        # Kill parent
        os.kill(pid, sig)

        # Wait for exit
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
                time.sleep(0.1)
            except ProcessLookupError:
                return True

        # Force kill
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        return True

    except ProcessLookupError:
        return True
    except PermissionError:
        logger.error(f"Permission denied killing PID {pid}")
        return False


def _get_child_pids(parent_pid: int) -> list[int]:
    """Get child PIDs of a process (Linux only)."""
    try:
        result = subprocess.run(
            ["pgrep", "-P", str(parent_pid)],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return [int(p) for p in result.stdout.strip().split("\n") if p.strip()]
    except Exception:
        pass
    return []


def is_port_in_use(port: int, *, host: str = "127.0.0.1") -> bool:
    """Check if a TCP port is in use."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex((host, port)) == 0


def wait_for_port(
    port: int,
    *,
    host: str = "127.0.0.1",
    timeout_ms: int = 30_000,
    poll_ms: int = 200,
) -> bool:
    """Wait for a port to become available."""
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        if is_port_in_use(port, host=host):
            return True
        time.sleep(poll_ms / 1000)
    return False


class GracefulShutdown:
    """Handles graceful shutdown with signal trapping."""

    def __init__(self) -> None:
        self._shutting_down = False
        self._callbacks: list[Any] = []

    def register(self, callback: Any) -> None:
        self._callbacks.append(callback)

    def install(self) -> None:
        """Install signal handlers for SIGTERM and SIGINT."""
        signal.signal(signal.SIGTERM, self._handle)
        signal.signal(signal.SIGINT, self._handle)

    @property
    def is_shutting_down(self) -> bool:
        return self._shutting_down

    def _handle(self, signum: int, frame: Any) -> None:
        if self._shutting_down:
            sys.exit(128 + signum)
        self._shutting_down = True
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        for cb in self._callbacks:
            try:
                cb()
            except Exception as e:
                logger.error(f"Shutdown callback error: {e}")


class ProcessWatchdog:
    """Monitors a process and restarts on unexpected exits."""

    def __init__(
        self,
        *,
        max_restarts: int = 5,
        window_ms: int = 300_000,
        cooldown_ms: int = 5_000,
    ):
        self._max_restarts = max_restarts
        self._window_ms = window_ms
        self._cooldown_ms = cooldown_ms
        self._restart_times: list[int] = []

    def record_exit(self) -> None:
        now = int(time.time() * 1000)
        self._restart_times.append(now)
        cutoff = now - self._window_ms
        self._restart_times = [t for t in self._restart_times if t > cutoff]

    def should_restart(self) -> bool:
        return len(self._restart_times) <= self._max_restarts

    @property
    def cooldown_seconds(self) -> float:
        return self._cooldown_ms / 1000
