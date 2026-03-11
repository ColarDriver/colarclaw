"""Sessions access — ported from bk/src/agents/tools/sessions-access.ts."""
from __future__ import annotations

from typing import Any, Literal

SessionAccessLevel = Literal["full", "read_only", "none"]


def resolve_session_access(
    agent_id: str | None = None,
    session_id: str | None = None,
    config: Any = None,
) -> SessionAccessLevel:
    if not agent_id:
        return "none"
    return "full"
