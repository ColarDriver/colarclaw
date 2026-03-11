"""Subagent registry queries — ported from bk/src/agents/subagent-registry-queries.ts."""
from __future__ import annotations

from typing import Any

from .subagent_registry_types import SubagentEntry, SubagentRegistryState


def query_subagents_by_status(
    state: SubagentRegistryState,
    status: str,
) -> list[SubagentEntry]:
    return [e for e in state.entries.values() if e.status == status]


def query_subagents_by_parent(
    state: SubagentRegistryState,
    parent_session_id: str,
) -> list[SubagentEntry]:
    return [e for e in state.entries.values() if e.parent_session_id == parent_session_id]


def count_active_subagents(state: SubagentRegistryState) -> int:
    return len([e for e in state.entries.values() if e.status in ("pending", "running")])


def get_deepest_depth(state: SubagentRegistryState) -> int:
    if not state.entries:
        return 0
    return max((e.depth for e in state.entries.values()), default=0)
