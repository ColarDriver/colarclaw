"""Subagent registry completion — ported from bk/src/agents/subagent-registry-completion.ts."""
from __future__ import annotations

import time
from typing import Any

from .subagent_registry_types import SubagentEntry, SubagentRegistryState


def mark_subagent_completed(
    state: SubagentRegistryState,
    entry_id: str,
    output: str | None = None,
    exit_code: int = 0,
) -> bool:
    entry = state.entries.get(entry_id)
    if not entry:
        return False
    entry.status = "completed"
    entry.ended_at = time.time() * 1000
    entry.exit_code = exit_code
    if output is not None:
        entry.output = output
    return True


def mark_subagent_failed(
    state: SubagentRegistryState,
    entry_id: str,
    error: str,
) -> bool:
    entry = state.entries.get(entry_id)
    if not entry:
        return False
    entry.status = "failed"
    entry.ended_at = time.time() * 1000
    entry.error = error
    return True
