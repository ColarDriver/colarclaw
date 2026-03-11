"""Bash tools exec — ported from bk/src/agents/bash-tools.exec.ts.

Main bash execution entry point.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("openclaw.agents.bash_tools_exec")


@dataclass
class BashExecRequest:
    command: str
    cwd: str | None = None
    timeout_ms: int = 120_000
    env: dict[str, str] | None = None
    background: bool = False
    approval_id: str | None = None


@dataclass
class BashExecResult:
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    duration_ms: float = 0
    pid: int | None = None


async def exec_bash(request: BashExecRequest) -> BashExecResult:
    """Execute a bash command asynchronously."""
    import time
    start = time.time()
    env = {**os.environ, **(request.env or {})}
    cwd = request.cwd or os.getcwd()
    timeout_s = request.timeout_ms / 1000

    try:
        proc = await asyncio.create_subprocess_shell(
            request.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd, env=env,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_s,
            )
            return BashExecResult(
                exit_code=proc.returncode or 0,
                stdout=stdout_bytes.decode("utf-8", errors="replace"),
                stderr=stderr_bytes.decode("utf-8", errors="replace"),
                duration_ms=(time.time() - start) * 1000,
                pid=proc.pid,
            )
        except asyncio.TimeoutError:
            proc.kill()
            return BashExecResult(
                exit_code=-1, timed_out=True,
                duration_ms=(time.time() - start) * 1000,
                pid=proc.pid,
            )
    except Exception as exc:
        return BashExecResult(
            exit_code=-1, stderr=str(exc),
            duration_ms=(time.time() - start) * 1000,
        )
