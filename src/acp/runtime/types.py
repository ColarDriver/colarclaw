"""ACP runtime types — ported from bk/src/acp/runtime/types.ts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

AcpRuntimeSessionMode = Literal["oneshot", "persistent"]


@dataclass
class AcpRuntimeSessionOptions:
    cwd: str | None = None
    tool_use: bool = True
    thinking: str | None = None
    verbose: bool = False
    system_prompt: str | None = None


@dataclass
class AcpRuntimeSession:
    session_key: str = ""
    agent: str = ""
    mode: AcpRuntimeSessionMode = "persistent"
    backend: str | None = None
    cwd: str | None = None
    runtime_options: AcpRuntimeSessionOptions = field(default_factory=AcpRuntimeSessionOptions)
