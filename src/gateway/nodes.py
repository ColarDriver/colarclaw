"""Gateway node management — ported from bk/src/gateway/node-registry.ts,
node-command-policy.ts, node-invoke-sanitize.ts,
node-invoke-system-run-approval.ts, node-invoke-system-run-approval-match.ts,
node-invoke-system-run-approval-errors.ts, server-node-events.ts,
server-node-events-types.ts, server-node-subscriptions.ts,
server-mobile-nodes.ts, server-model-catalog.ts.

Node registration, command policy, system run approval, and node event handling.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

logger = logging.getLogger(__name__)


# ─── node-invoke-system-run-approval-errors.ts ───

class NodeApprovalRequiredError(Exception):
    """Raised when a node invoke requires approval."""
    def __init__(self, command: str, node_id: str | None = None) -> None:
        msg = f'command "{command}" requires approval'
        if node_id:
            msg += f" on node {node_id}"
        super().__init__(msg)
        self.command = command
        self.node_id = node_id


class NodeApprovalDeniedError(Exception):
    """Raised when a node invoke approval is denied."""
    def __init__(self, command: str, reason: str = "") -> None:
        msg = f'command "{command}" approval denied'
        if reason:
            msg += f": {reason}"
        super().__init__(msg)
        self.command = command
        self.reason = reason


# ─── node-invoke-sanitize.ts ───

def sanitize_node_invoke_command(command: str) -> str:
    """Sanitize a node invoke command, removing dangerous patterns."""
    sanitized = command.strip()
    # Remove null bytes
    sanitized = sanitized.replace("\x00", "")
    return sanitized


# ─── node-invoke-system-run-approval-match.ts ───

@dataclass
class ApprovalMatchRule:
    """A rule for matching commands that need approval."""
    pattern: str = ""
    action: str = "require"  # "require" | "allow" | "deny"
    regex: re.Pattern | None = None

    def __post_init__(self) -> None:
        if self.pattern and not self.regex:
            try:
                self.regex = re.compile(self.pattern)
            except re.error:
                self.regex = None


def match_approval_rule(
    command: str,
    rules: list[ApprovalMatchRule],
) -> ApprovalMatchRule | None:
    """Find the first matching approval rule for a command."""
    for rule in rules:
        if rule.regex and rule.regex.search(command):
            return rule
    return None


# ─── node-invoke-system-run-approval.ts ───

@dataclass
class SystemRunApprovalConfig:
    """Configuration for system run approvals."""
    enabled: bool = False
    default_action: str = "require"  # "require" | "allow" | "deny"
    rules: list[ApprovalMatchRule] = field(default_factory=list)


def resolve_system_run_approval(
    *,
    command: str,
    config: SystemRunApprovalConfig,
    node_id: str | None = None,
) -> str:
    """Resolve whether a system run command needs approval.

    Returns: "allow", "require", or "deny"
    """
    if not config.enabled:
        return "allow"

    sanitized = sanitize_node_invoke_command(command)
    if not sanitized:
        return "deny"

    rule = match_approval_rule(sanitized, config.rules)
    if rule:
        return rule.action

    return config.default_action


# ─── node-command-policy.ts ───

@dataclass
class NodeCommandPolicy:
    """Policy for commands a node is allowed to execute."""
    allow_patterns: list[str] = field(default_factory=list)
    deny_patterns: list[str] = field(default_factory=list)
    max_concurrent: int = 5
    timeout_ms: int = 300_000  # 5 minutes
    require_approval: bool = False


def check_node_command_policy(
    command: str,
    policy: NodeCommandPolicy,
) -> tuple[bool, str]:
    """Check if a command is allowed by the node policy.

    Returns (allowed, reason).
    """
    # Check deny patterns first
    for pattern in policy.deny_patterns:
        try:
            if re.search(pattern, command):
                return False, f"command matches deny pattern: {pattern}"
        except re.error:
            continue

    # Check allow patterns
    if policy.allow_patterns:
        for pattern in policy.allow_patterns:
            try:
                if re.search(pattern, command):
                    return True, ""
            except re.error:
                continue
        return False, "command does not match any allow pattern"

    return True, ""


# ─── node-registry.ts ───

@dataclass
class RegisteredNode:
    """A registered compute node."""
    node_id: str = ""
    display_name: str = ""
    platform: str = ""
    hostname: str = ""
    os_info: str = ""
    arch: str = ""
    capabilities: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    conn_id: str = ""
    connected_at_ms: int = 0
    last_seen_ms: int = 0
    status: str = "online"  # "online" | "offline" | "busy"
    active_invocations: int = 0
    max_concurrent: int = 5
    policy: NodeCommandPolicy = field(default_factory=NodeCommandPolicy)


class NodeRegistry:
    """Registry for compute nodes connected to the gateway."""

    def __init__(self) -> None:
        self._nodes: dict[str, RegisteredNode] = {}

    def register(self, node: RegisteredNode) -> None:
        self._nodes[node.node_id] = node

    def unregister(self, node_id: str) -> RegisteredNode | None:
        return self._nodes.pop(node_id, None)

    def get(self, node_id: str) -> RegisteredNode | None:
        return self._nodes.get(node_id)

    def list(self) -> list[RegisteredNode]:
        return list(self._nodes.values())

    def list_online(self) -> list[RegisteredNode]:
        return [n for n in self._nodes.values() if n.status == "online"]

    def update_last_seen(self, node_id: str) -> None:
        node = self._nodes.get(node_id)
        if node:
            node.last_seen_ms = int(time.time() * 1000)

    def set_status(self, node_id: str, status: str) -> None:
        node = self._nodes.get(node_id)
        if node:
            node.status = status

    def increment_invocations(self, node_id: str) -> None:
        node = self._nodes.get(node_id)
        if node:
            node.active_invocations += 1

    def decrement_invocations(self, node_id: str) -> None:
        node = self._nodes.get(node_id)
        if node and node.active_invocations > 0:
            node.active_invocations -= 1

    def find_available_node(
        self,
        *,
        capabilities: list[str] | None = None,
        command: str | None = None,
    ) -> RegisteredNode | None:
        """Find an available node, optionally filtered by capabilities and command policy."""
        candidates = self.list_online()
        if capabilities:
            candidates = [
                n for n in candidates
                if all(cap in n.capabilities for cap in capabilities)
            ]
        if command:
            candidates = [
                n for n in candidates
                if check_node_command_policy(command, n.policy)[0]
            ]
        # Prefer nodes with fewer active invocations
        candidates.sort(key=lambda n: n.active_invocations)
        for node in candidates:
            if node.active_invocations < node.max_concurrent:
                return node
        return None

    def clear(self) -> None:
        self._nodes.clear()


# ─── server-node-events-types.ts ───

@dataclass
class NodeEvent:
    """An event from a compute node."""
    type: str = ""  # "invoke.result", "invoke.error", "invoke.progress", etc.
    node_id: str = ""
    invoke_id: str = ""
    payload: Any = None
    timestamp_ms: int = 0


# ─── server-node-subscriptions.ts ───

class NodeSubscriptionRegistry:
    """Tracks which connections are subscribed to node events."""

    def __init__(self) -> None:
        self._subscriptions: dict[str, set[str]] = {}  # node_id -> set of conn_ids

    def subscribe(self, node_id: str, conn_id: str) -> None:
        if node_id not in self._subscriptions:
            self._subscriptions[node_id] = set()
        self._subscriptions[node_id].add(conn_id)

    def unsubscribe(self, node_id: str, conn_id: str) -> None:
        subs = self._subscriptions.get(node_id)
        if subs:
            subs.discard(conn_id)
            if not subs:
                del self._subscriptions[node_id]

    def unsubscribe_all(self, conn_id: str) -> None:
        """Remove a connection from all node subscriptions."""
        empty_nodes = []
        for node_id, subs in self._subscriptions.items():
            subs.discard(conn_id)
            if not subs:
                empty_nodes.append(node_id)
        for node_id in empty_nodes:
            del self._subscriptions[node_id]

    def get_subscribers(self, node_id: str) -> set[str]:
        return self._subscriptions.get(node_id, set())


# ─── server-mobile-nodes.ts ───

def is_mobile_node_platform(platform: str) -> bool:
    """Check if a platform string indicates a mobile device."""
    p = platform.strip().lower()
    return p in ("ios", "android", "ipados")


# ─── server-model-catalog.ts ───

@dataclass
class ModelCatalogEntry:
    """An entry in the model catalog."""
    provider: str = ""
    model: str = ""
    display_name: str = ""
    context_window: int = 0
    supports_tools: bool = False
    supports_vision: bool = False
    supports_thinking: bool = False
