"""Tool policy conformance — ported from bk/src/agents/tool-policy-conformance.ts.

Conformance checking for tool policy results.
"""
from __future__ import annotations

from typing import Any

from .tool_policy import PolicyDecision, ToolPolicyResult


def check_tool_policy_conformance(
    result: ToolPolicyResult,
    *,
    fail_on_deny: bool = True,
    fail_on_ask: bool = False,
) -> bool:
    """Check if a tool policy result conforms to expectations.

    Returns True if the tool should be allowed, False otherwise.
    """
    if result.decision == "allow":
        return True
    if result.decision == "deny" and fail_on_deny:
        return False
    if result.decision == "ask" and fail_on_ask:
        return False
    return True


def format_policy_denial(result: ToolPolicyResult, tool_id: str) -> str:
    """Format a human-readable denial message."""
    reason = result.reason or "denied by policy"
    source = f" (source: {result.source})" if result.source else ""
    return f"Tool '{tool_id}' is not allowed: {reason}{source}"


def aggregate_policy_results(
    results: list[tuple[str, ToolPolicyResult]],
) -> PolicyDecision:
    """Aggregate multiple policy results into a single decision."""
    for _name, result in results:
        if result.decision == "deny":
            return "deny"
    for _name, result in results:
        if result.decision == "ask":
            return "ask"
    return "allow"
