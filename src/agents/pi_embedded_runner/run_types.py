"""Pi embedded runner run types — ported from bk/src/agents/pi-embedded-runner/run/types.ts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

RunStatus = Literal["pending", "running", "completed", "failed", "cancelled"]


@dataclass
class RunParams:
    session_id: str = ""
    message: str = ""
    model: str | None = None
    provider: str | None = None
    system_prompt: str | None = None
    tools: list[dict[str, Any]] | None = None
    max_turns: int = 100
    timeout_ms: int = 600_000


@dataclass
class RunResult:
    status: RunStatus = "pending"
    output: str | None = None
    tool_calls_count: int = 0
    turns: int = 0
    total_tokens: int = 0
    duration_ms: float = 0
    error: str | None = None
