"""Tool policy shared — ported from bk/src/agents/tool-policy-shared.ts.

Shared types and helpers for tool policy evaluation.
"""
from __future__ import annotations

from typing import Any, Literal

PolicyDecision = Literal["allow", "deny", "ask"]

# Tools that are always allowed regardless of policy
ALWAYS_ALLOWED_TOOLS = frozenset({
    "session_status",
})

# Tools that require explicit allow
RESTRICTED_TOOLS = frozenset({
    "exec",
    "process",
    "write",
    "edit",
    "apply_patch",
})


def is_always_allowed(tool_id: str) -> bool:
    """Check if a tool is always allowed regardless of policy."""
    return tool_id in ALWAYS_ALLOWED_TOOLS


def is_restricted_tool(tool_id: str) -> bool:
    """Check if a tool requires explicit policy allowance."""
    return tool_id in RESTRICTED_TOOLS


def normalize_tool_id(tool_id: str) -> str:
    """Normalize a tool ID for comparison."""
    return tool_id.strip().lower()
