"""Subagent registry — ported from bk/src/agents/subagent-registry*.ts.

Central registry for tracking sub-agent lifecycle, state, and queries.
"""
from __future__ import annotations
import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

log = logging.getLogger("openclaw.agents.subagent_registry")

SubagentState = Literal["pending", "running", "completed", "failed", "cancelled"]

@dataclass
class SubagentEntry:
    id: str
    session_key: str
    parent_session_key: str
    parent_run_id: str | None = None
    state: SubagentState = "pending"
    task: str = ""
    model: str | None = None
    depth: int = 0
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    result: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class SubagentRegistryStats:
    total: int = 0
    pending: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0

class SubagentRegistry:
    def __init__(self, max_depth: int = 5, max_concurrent: int = 10):
        self._entries: dict[str, SubagentEntry] = {}
        self._max_depth = max_depth
        self._max_concurrent = max_concurrent
        self._lock = asyncio.Lock()

    @property
    def max_depth(self) -> int:
        return self._max_depth

    @property
    def max_concurrent(self) -> int:
        return self._max_concurrent

    async def register(self, entry: SubagentEntry) -> None:
        async with self._lock:
            if entry.depth > self._max_depth:
                raise ValueError(f"Max subagent depth {self._max_depth} exceeded")
            active = sum(1 for e in self._entries.values() if e.state in ("pending", "running"))
            if active >= self._max_concurrent:
                raise RuntimeError(f"Max concurrent subagents {self._max_concurrent} reached")
            self._entries[entry.id] = entry
            log.info("Registered subagent %s (depth=%d, parent=%s)", entry.id, entry.depth, entry.parent_session_key)

    async def update_state(self, agent_id: str, state: SubagentState, **kwargs: Any) -> None:
        entry = self._entries.get(agent_id)
        if not entry:
            return
        entry.state = state
        if state == "running" and not entry.started_at:
            entry.started_at = time.time()
        if state in ("completed", "failed", "cancelled"):
            entry.completed_at = time.time()
        entry.result = kwargs.get("result", entry.result)
        entry.error = kwargs.get("error", entry.error)

    async def get(self, agent_id: str) -> SubagentEntry | None:
        return self._entries.get(agent_id)

    async def list_by_parent(self, parent_session_key: str) -> list[SubagentEntry]:
        return [e for e in self._entries.values() if e.parent_session_key == parent_session_key]

    async def list_active(self) -> list[SubagentEntry]:
        return [e for e in self._entries.values() if e.state in ("pending", "running")]

    def stats(self) -> SubagentRegistryStats:
        s = SubagentRegistryStats(total=len(self._entries))
        for e in self._entries.values():
            if e.state == "pending": s.pending += 1
            elif e.state == "running": s.running += 1
            elif e.state == "completed": s.completed += 1
            elif e.state == "failed": s.failed += 1
            elif e.state == "cancelled": s.cancelled += 1
        return s

    async def cleanup(self, max_age_seconds: float = 3600) -> int:
        now = time.time()
        to_remove = [
            k for k, v in self._entries.items()
            if v.state in ("completed", "failed", "cancelled") and (now - v.created_at) > max_age_seconds
        ]
        for k in to_remove:
            del self._entries[k]
        return len(to_remove)
