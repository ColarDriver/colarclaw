"""Bash tools exec approval request — ported from bk/src/agents/bash-tools.exec-approval-request.ts."""
from __future__ import annotations

import re
from typing import Any

from .bash_tools_exec_types import ExecApprovalPolicy, ExecApprovalRequest, ExecApprovalResult

DANGEROUS_PATTERNS = [
    re.compile(r"\brm\s+-rf\b", re.IGNORECASE),
    re.compile(r"\bsudo\b", re.IGNORECASE),
    re.compile(r"\bmkfs\b", re.IGNORECASE),
    re.compile(r"\bdd\s+if=", re.IGNORECASE),
    re.compile(r"\bformat\b", re.IGNORECASE),
    re.compile(r"\bfdisk\b", re.IGNORECASE),
]


def is_dangerous_command(command: str) -> bool:
    return any(p.search(command) for p in DANGEROUS_PATTERNS)


def evaluate_exec_approval(request: ExecApprovalRequest) -> ExecApprovalResult:
    if request.policy == "always_allow":
        return ExecApprovalResult(approved=True, policy=request.policy)
    if request.policy == "always_deny":
        return ExecApprovalResult(approved=False, policy=request.policy, reason="Policy denies all commands")
    if request.policy == "auto":
        if is_dangerous_command(request.command):
            return ExecApprovalResult(approved=False, policy=request.policy, reason="Dangerous command detected")
        return ExecApprovalResult(approved=True, policy=request.policy)
    return ExecApprovalResult(approved=False, policy="ask", reason="Requires approval")
