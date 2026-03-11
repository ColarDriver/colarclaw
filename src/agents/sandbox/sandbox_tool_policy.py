"""Sandbox tool policy — ported from bk/src/agents/sandbox-tool-policy.ts."""
from __future__ import annotations

from typing import Any


def resolve_sandbox_tool_policy(config: Any = None) -> dict[str, Any]:
    """Resolve sandbox-level tool policy."""
    if not config:
        return {"allowed": None, "blocked": None}
    sandbox = getattr(config, "sandbox", None)
    if not sandbox:
        return {"allowed": None, "blocked": None}
    policy = getattr(sandbox, "tool_policy", None)
    if not policy:
        return {"allowed": None, "blocked": None}
    return {
        "allowed": getattr(policy, "allowed_tools", None),
        "blocked": getattr(policy, "blocked_tools", None),
    }
