from __future__ import annotations

from dataclasses import dataclass, field

from memory.types import MemorySearchResult


@dataclass
class ToolEvent:
    name: str
    args: dict[str, object]
    result: str


@dataclass
class GraphState:
    run_id: str
    session_id: str
    user_message: str
    model: str | None = None
    retrieved_context: list[MemorySearchResult] = field(default_factory=list)
    planned_tools: list[dict[str, object]] = field(default_factory=list)
    tool_events: list[ToolEvent] = field(default_factory=list)
    response_text: str = ""
