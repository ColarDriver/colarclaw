"""Bash tools — ported from bk/src/agents/bash-tools*.ts.

Bash/shell command execution, process management, and approval flow.
"""
from __future__ import annotations
import asyncio
import logging
import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Literal

log = logging.getLogger("openclaw.agents.bash_tools")

ExecApprovalStatus = Literal["approved", "denied", "pending"]

@dataclass
class BashExecRequest:
    command: str
    cwd: str | None = None
    timeout_ms: float = 30_000
    env: dict[str, str] | None = None

@dataclass
class BashExecResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    duration_ms: float = 0
    killed: bool = False

@dataclass
class BashExecApprovalRequest:
    command: str
    cwd: str | None = None
    tool_call_id: str | None = None
    reason: str | None = None

@dataclass
class ProcessInfo:
    pid: int
    command: str
    cwd: str | None = None
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    exit_code: int | None = None

class BashProcessRegistry:
    def __init__(self):
        self._processes: dict[int, ProcessInfo] = {}

    def register(self, pid: int, command: str, cwd: str | None = None) -> ProcessInfo:
        info = ProcessInfo(pid=pid, command=command, cwd=cwd)
        self._processes[pid] = info
        return info

    def unregister(self, pid: int) -> None:
        self._processes.pop(pid, None)

    def get(self, pid: int) -> ProcessInfo | None:
        return self._processes.get(pid)

    def list_active(self) -> list[ProcessInfo]:
        return [p for p in self._processes.values() if p.completed_at is None]

    def mark_completed(self, pid: int, exit_code: int) -> None:
        info = self._processes.get(pid)
        if info:
            info.completed_at = time.time()
            info.exit_code = exit_code

    def kill_all(self) -> int:
        count = 0
        for info in self.list_active():
            try:
                os.kill(info.pid, signal.SIGKILL)
                count += 1
            except ProcessLookupError:
                pass
        return count

async def exec_bash(request: BashExecRequest) -> BashExecResult:
    """Execute a bash command asynchronously."""
    start = time.time()
    env = {**os.environ, **(request.env or {})}
    timeout_sec = request.timeout_ms / 1000
    try:
        proc = await asyncio.create_subprocess_shell(
            request.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=request.cwd,
            env=env,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
            return BashExecResult(
                exit_code=proc.returncode or 0,
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                duration_ms=(time.time() - start) * 1000,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return BashExecResult(
                exit_code=-1, stdout="", stderr="Command timed out",
                timed_out=True, killed=True,
                duration_ms=(time.time() - start) * 1000,
            )
    except Exception as e:
        return BashExecResult(
            exit_code=-1, stdout="", stderr=str(e),
            duration_ms=(time.time() - start) * 1000,
        )

def is_dangerous_command(command: str) -> bool:
    dangerous = ["rm -rf /", "mkfs", "dd if=", "> /dev/sda", ":(){ :|:& };:"]
    lower = command.lower().strip()
    return any(d in lower for d in dangerous)

def sanitize_command_output(output: str, max_length: int = 50_000) -> str:
    if len(output) <= max_length:
        return output
    half = max_length // 2
    return output[:half] + f"\n\n... [{len(output) - max_length} chars truncated] ...\n\n" + output[-half:]
