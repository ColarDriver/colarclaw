"""Spawned context — ported from bk/src/agents/spawned-context.ts."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass
class SpawnedContext:
    session_key: str
    parent_session_key: str
    depth: int = 0
    workspace_dir: str = ""
    model: str | None = None
    thinking: str | None = None
    task: str = ""
    run_id: str | None = None
    attachments: list[dict[str, Any]] = field(default_factory=list)

def is_spawned_context(ctx: Any) -> bool:
    return isinstance(ctx, SpawnedContext)

def create_spawned_context(
    session_key: str, parent_session_key: str, task: str, **kwargs: Any,
) -> SpawnedContext:
    return SpawnedContext(
        session_key=session_key,
        parent_session_key=parent_session_key,
        task=task,
        **kwargs,
    )
