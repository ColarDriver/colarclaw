"""Subagent registry state — ported from bk/src/agents/subagent-registry-state.ts."""
from __future__ import annotations

import time
from typing import Any

from .subagent_registry_types import SubagentEntry, SubagentRegistryState, SubagentStatus


class SubagentRegistryStateManager:
    """Manages subagent registry state."""

    def __init__(self, max_concurrent: int = 5, max_depth: int = 3):
        self._state = SubagentRegistryState(max_concurrent=max_concurrent, max_depth=max_depth)

    @property
    def state(self) -> SubagentRegistryState:
        return self._state

    def register(self, entry: SubagentEntry) -> None:
        self._state.entries[entry.id] = entry

    def get(self, entry_id: str) -> SubagentEntry | None:
        return self._state.entries.get(entry_id)

    def update_status(self, entry_id: str, status: SubagentStatus, **kwargs: Any) -> None:
        entry = self._state.entries.get(entry_id)
        if not entry:
            return
        entry.status = status
        if status == "running" and not entry.started_at:
            entry.started_at = time.time() * 1000
        if status in ("completed", "failed", "cancelled"):
            entry.ended_at = time.time() * 1000
        for key, val in kwargs.items():
            if hasattr(entry, key):
                setattr(entry, key, val)

    def remove(self, entry_id: str) -> None:
        self._state.entries.pop(entry_id, None)

    def list_active(self) -> list[SubagentEntry]:
        return [e for e in self._state.entries.values() if e.status in ("pending", "running")]

    def list_all(self) -> list[SubagentEntry]:
        return list(self._state.entries.values())

    def can_spawn(self) -> bool:
        active = len(self.list_active())
        return active < self._state.max_concurrent
