"""Bash tools exec host node — ported from bk/src/agents/bash-tools.exec-host-node.ts."""
from __future__ import annotations

import asyncio
from typing import Any

from .bash_tools_exec import BashExecRequest, BashExecResult, exec_bash
from .bash_tools_exec_host_shared import build_exec_env, resolve_exec_cwd, resolve_exec_shell


async def exec_on_host(
    command: str,
    cwd: str | None = None,
    workspace_dir: str | None = None,
    timeout_ms: int = 120_000,
    env: dict[str, str] | None = None,
) -> BashExecResult:
    """Execute a command on the host machine."""
    resolved_cwd = resolve_exec_cwd(cwd, workspace_dir)
    full_env = build_exec_env(env)

    return await exec_bash(BashExecRequest(
        command=command,
        cwd=resolved_cwd,
        timeout_ms=timeout_ms,
        env=full_env,
    ))
