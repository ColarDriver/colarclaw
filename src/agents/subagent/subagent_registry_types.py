"""Subagent registry types — ported from bk/src/agents/subagent-registry.types.ts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

SubagentStatus = Literal["pending", "running", "completed", "failed", "cancelled"]


@dataclass
class SubagentEntry:
    id: str = ""
    name: str = ""
    session_id: str | None = None
    parent_session_id: str | None = None
    status: SubagentStatus = "pending"
    model: str | None = None
    provider: str | None = None
    created_at: float = 0
    started_at: float | None = None
    ended_at: float | None = None
    exit_code: int | None = None
    error: str | None = None
    output: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    depth: int = 0


@dataclass
class SubagentRegistryState:
    entries: dict[str, SubagentEntry] = field(default_factory=dict)
    max_concurrent: int = 5
    max_depth: int = 3
