"""Bash tools exec types — ported from bk/src/agents/bash-tools.exec-types.ts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ExecApprovalPolicy = Literal["always_allow", "always_deny", "ask", "auto"]


@dataclass
class ExecApprovalRequest:
    command: str
    cwd: str | None = None
    policy: ExecApprovalPolicy = "ask"
    reason: str | None = None


@dataclass
class ExecApprovalResult:
    approved: bool = False
    policy: ExecApprovalPolicy = "ask"
    reason: str | None = None
