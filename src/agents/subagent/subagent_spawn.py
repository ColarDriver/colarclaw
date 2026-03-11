"""Subagent spawn — ported from bk/src/agents/subagent-spawn.ts."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass
class SubagentSpawnRequest:
    task: str
    parent_session_key: str
    parent_run_id: str | None = None
    model: str | None = None
    thinking: str | None = None
    depth: int = 0
    attachments: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class SubagentSpawnResult:
    agent_id: str
    session_key: str
    success: bool = True
    error: str | None = None

def validate_spawn_request(request: SubagentSpawnRequest, max_depth: int = 5) -> str | None:
    if not request.task or not request.task.strip():
        return "Task cannot be empty"
    if request.depth >= max_depth:
        return f"Max depth ({max_depth}) exceeded"
    if not request.parent_session_key:
        return "Parent session key required"
    return None
