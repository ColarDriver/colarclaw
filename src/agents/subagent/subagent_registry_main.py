"""Subagent registry — ported from bk/src/agents/subagent-registry.ts.

Main subagent registry combining state, queries, completion, and cleanup.
"""
from __future__ import annotations

import logging
from typing import Any

from .subagent_registry_state import SubagentRegistryStateManager
from .subagent_registry_types import SubagentEntry, SubagentStatus

log = logging.getLogger("openclaw.agents.subagent_registry")


class SubagentRegistry:
    """Central registry for managing subagent lifecycles."""

    def __init__(self, max_concurrent: int = 5, max_depth: int = 3):
        self._state = SubagentRegistryStateManager(max_concurrent, max_depth)

    def register(self, entry: SubagentEntry) -> bool:
        if not self._state.can_spawn():
            log.warning("Max concurrent subagents reached, cannot register %s", entry.id)
            return False
        self._state.register(entry)
        return True

    def get(self, entry_id: str) -> SubagentEntry | None:
        return self._state.get(entry_id)

    def update_status(self, entry_id: str, status: SubagentStatus, **kwargs: Any) -> None:
        self._state.update_status(entry_id, status, **kwargs)

    def complete(self, entry_id: str, output: str | None = None, exit_code: int = 0) -> None:
        self._state.update_status(entry_id, "completed", output=output, exit_code=exit_code)

    def fail(self, entry_id: str, error: str) -> None:
        self._state.update_status(entry_id, "failed", error=error)

    def cancel(self, entry_id: str) -> None:
        self._state.update_status(entry_id, "cancelled")

    def remove(self, entry_id: str) -> None:
        self._state.remove(entry_id)

    def list_active(self) -> list[SubagentEntry]:
        return self._state.list_active()

    def list_all(self) -> list[SubagentEntry]:
        return self._state.list_all()

    def can_spawn(self) -> bool:
        return self._state.can_spawn()

    def cleanup_completed(self, max_age_ms: float = 3600_000) -> int:
        import time
        now = time.time() * 1000
        to_remove = []
        for entry in self._state.list_all():
            if entry.status in ("completed", "failed", "cancelled"):
                if entry.ended_at and (now - entry.ended_at) > max_age_ms:
                    to_remove.append(entry.id)
        for eid in to_remove:
            self._state.remove(eid)
        return len(to_remove)
