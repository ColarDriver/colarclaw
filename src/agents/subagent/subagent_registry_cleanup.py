"""Subagent registry cleanup — ported from bk/src/agents/subagent-registry-cleanup.ts."""
from __future__ import annotations

import time
from .subagent_registry_types import SubagentRegistryState

DEFAULT_CLEANUP_MAX_AGE_MS = 3600_000


def cleanup_completed_subagents(
    state: SubagentRegistryState,
    max_age_ms: float = DEFAULT_CLEANUP_MAX_AGE_MS,
) -> list[str]:
    now = time.time() * 1000
    removed: list[str] = []
    for eid, entry in list(state.entries.items()):
        if entry.status in ("completed", "failed", "cancelled"):
            if entry.ended_at and (now - entry.ended_at) > max_age_ms:
                del state.entries[eid]
                removed.append(eid)
    return removed
