"""Agent step tool — ported from bk/src/agents/tools/agent-step.ts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AgentStepInput:
    message: str = ""
    context: dict[str, Any] | None = None


@dataclass
class AgentStepOutput:
    response: str = ""
    tool_calls: list[dict[str, Any]] | None = None
    finished: bool = False


AGENT_STEP_TOOL_NAME = "agent_step"
AGENT_STEP_SCHEMA = {
    "type": "object",
    "properties": {
        "message": {"type": "string", "description": "The message to process"},
    },
    "required": ["message"],
}
