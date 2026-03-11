"""Subagent registry runtime — ported from bk/src/agents/subagent-registry-runtime.ts."""
from __future__ import annotations

from typing import Any

from .subagent_registry_types import SubagentEntry, SubagentRegistryState


def resolve_runtime_subagent_context(
    state: SubagentRegistryState,
    entry_id: str,
) -> dict[str, Any]:
    entry = state.entries.get(entry_id)
    if not entry:
        return {}
    return {
        "id": entry.id,
        "name": entry.name,
        "session_id": entry.session_id,
        "parent_session_id": entry.parent_session_id,
        "depth": entry.depth,
        "status": entry.status,
        "model": entry.model,
        "provider": entry.provider,
    }
