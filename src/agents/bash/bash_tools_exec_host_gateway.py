"""Bash tools exec host gateway — ported from bk/src/agents/bash-tools.exec-host-gateway.ts."""
from __future__ import annotations

import asyncio
from typing import Any

from .bash_tools_exec import BashExecRequest, BashExecResult, exec_bash
from .bash_tools_exec_host_shared import build_exec_env, resolve_exec_cwd


async def exec_on_gateway(
    command: str,
    cwd: str | None = None,
    timeout_ms: int = 120_000,
    env: dict[str, str] | None = None,
    gateway_url: str | None = None,
) -> BashExecResult:
    """Execute a command on a remote gateway (or locally as fallback)."""
    if gateway_url:
        # In a full implementation, this would POST to the gateway API
        pass
    resolved_cwd = resolve_exec_cwd(cwd)
    full_env = build_exec_env(env)
    return await exec_bash(BashExecRequest(
        command=command, cwd=resolved_cwd,
        timeout_ms=timeout_ms, env=full_env,
    ))
