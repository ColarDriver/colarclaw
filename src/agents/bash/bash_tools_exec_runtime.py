"""Bash tools exec runtime — ported from bk/src/agents/bash-tools.exec-runtime.ts."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from .bash_tools_exec import BashExecRequest, BashExecResult, exec_bash
from .bash_tools_exec_approval_request import evaluate_exec_approval
from .bash_tools_exec_types import ExecApprovalPolicy, ExecApprovalRequest

log = logging.getLogger("openclaw.agents.bash_tools_exec_runtime")


async def exec_bash_with_approval(
    command: str,
    cwd: str | None = None,
    timeout_ms: int = 120_000,
    env: dict[str, str] | None = None,
    policy: ExecApprovalPolicy = "auto",
) -> BashExecResult:
    """Execute a bash command with approval check."""
    approval = evaluate_exec_approval(ExecApprovalRequest(
        command=command, cwd=cwd, policy=policy,
    ))
    if not approval.approved:
        from .bash_tools_exec import BashExecResult
        return BashExecResult(exit_code=-1, stderr=f"Command not approved: {approval.reason}")

    return await exec_bash(BashExecRequest(
        command=command, cwd=cwd, timeout_ms=timeout_ms, env=env,
    ))
