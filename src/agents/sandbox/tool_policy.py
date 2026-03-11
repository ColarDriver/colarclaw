"""Sandbox tool policy — ported from bk/src/agents/sandbox/tool-policy.ts."""
from __future__ import annotations

from typing import Any

from .types import SandboxToolPolicy, SandboxToolPolicyResolved


def resolve_sandbox_tool_policy_for_agent(
    config: Any = None,
) -> SandboxToolPolicyResolved:
    if not config:
        return SandboxToolPolicyResolved(policy=SandboxToolPolicy())
    sandbox = getattr(config, "sandbox", None)
    if not sandbox:
        return SandboxToolPolicyResolved(policy=SandboxToolPolicy())
    tool_policy = getattr(sandbox, "tool_policy", None)
    if not tool_policy:
        return SandboxToolPolicyResolved(policy=SandboxToolPolicy())
    return SandboxToolPolicyResolved(
        policy=SandboxToolPolicy(
            allowed_tools=getattr(tool_policy, "allowed_tools", None),
            blocked_tools=getattr(tool_policy, "blocked_tools", None),
            source=getattr(tool_policy, "source", "default"),
        ),
    )
