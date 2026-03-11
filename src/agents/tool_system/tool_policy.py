"""Tool policy — ported from bk/src/agents/tool-policy.ts.

Tool policy evaluation for enabling/disabling tools.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

PolicyDecision = Literal["allow", "deny", "ask"]


@dataclass
class ToolPolicyResult:
    decision: PolicyDecision = "allow"
    reason: str | None = None
    source: str | None = None


@dataclass
class ToolPolicyRule:
    tool_id: str | None = None
    tool_pattern: str | None = None
    decision: PolicyDecision = "allow"
    reason: str | None = None

    def matches(self, tool_id: str) -> bool:
        if self.tool_id and self.tool_id == tool_id:
            return True
        if self.tool_pattern:
            import fnmatch
            return fnmatch.fnmatch(tool_id, self.tool_pattern)
        return False


@dataclass
class ToolPolicy:
    rules: list[ToolPolicyRule] = field(default_factory=list)
    default_decision: PolicyDecision = "allow"


def evaluate_tool_policy(
    policy: ToolPolicy,
    tool_id: str,
) -> ToolPolicyResult:
    """Evaluate a tool policy for a given tool ID."""
    for rule in policy.rules:
        if rule.matches(tool_id):
            return ToolPolicyResult(
                decision=rule.decision,
                reason=rule.reason,
                source=f"rule:{rule.tool_id or rule.tool_pattern}",
            )
    return ToolPolicyResult(decision=policy.default_decision)


def create_tool_policy(
    allow: list[str] | None = None,
    deny: list[str] | None = None,
    default: PolicyDecision = "allow",
) -> ToolPolicy:
    """Create a tool policy from allow/deny lists."""
    rules: list[ToolPolicyRule] = []
    if allow:
        for tool_id in allow:
            rules.append(ToolPolicyRule(tool_id=tool_id, decision="allow"))
    if deny:
        for tool_id in deny:
            rules.append(ToolPolicyRule(tool_id=tool_id, decision="deny"))
    return ToolPolicy(rules=rules, default_decision=default)
