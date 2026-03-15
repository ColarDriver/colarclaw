"""Agent runner — types for run state and results.

Ported from openclaw/src/agents/pi-embedded-runner/types.ts
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ...memory.types import MemorySearchResult


@dataclass
class ToolEvent:
    name: str
    args: dict[str, object]
    result: str


@dataclass
class AgentRunState:
    """Mutable state for a single agent run cycle."""
    run_id: str
    session_id: str
    user_message: str
    model: str | None = None
    retrieved_context: list[MemorySearchResult] = field(default_factory=list)
    planned_tools: list[dict[str, object]] = field(default_factory=list)
    tool_events: list[ToolEvent] = field(default_factory=list)
    response_text: str = ""


@dataclass
class AgentRunMeta:
    """Metadata about a completed agent run."""
    session_id: str
    provider: str = ""
    model: str = ""
    usage: dict[str, int | None] | None = None


@dataclass
class AgentRunResult:
    """Result of a completed agent run."""
    text: str
    state: AgentRunState
    meta: AgentRunMeta | None = None
