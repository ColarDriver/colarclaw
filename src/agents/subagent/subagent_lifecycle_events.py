"""Subagent lifecycle events — ported from bk/src/agents/subagent-lifecycle-events.ts."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Literal

SubagentEvent = Literal["spawn", "start", "complete", "fail", "cancel", "timeout"]

@dataclass
class SubagentLifecycleEvent:
    event: SubagentEvent
    agent_id: str
    session_key: str
    parent_session_key: str
    timestamp: float
    metadata: dict[str, Any] | None = None

def create_lifecycle_event(
    event: SubagentEvent, agent_id: str, session_key: str,
    parent_session_key: str, timestamp: float, **metadata: Any,
) -> SubagentLifecycleEvent:
    return SubagentLifecycleEvent(
        event=event, agent_id=agent_id, session_key=session_key,
        parent_session_key=parent_session_key, timestamp=timestamp,
        metadata=metadata if metadata else None,
    )
