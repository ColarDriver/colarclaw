"""Sandbox runtime status — ported from bk/src/agents/sandbox/runtime-status.ts."""
from __future__ import annotations

from typing import Any, Literal

SandboxRuntimeStatus = Literal["ready", "not_configured", "docker_not_found", "container_failed"]


def resolve_sandbox_runtime_status(
    config: Any = None,
) -> SandboxRuntimeStatus:
    if not config:
        return "not_configured"
    sandbox = getattr(config, "sandbox", None)
    if not sandbox or not getattr(sandbox, "enabled", False):
        return "not_configured"
    return "ready"


def format_sandbox_tool_policy_blocked_message(
    tool_name: str,
    reason: str | None = None,
) -> str:
    base = f"Tool '{tool_name}' is blocked by sandbox policy"
    if reason:
        return f"{base}: {reason}"
    return base
