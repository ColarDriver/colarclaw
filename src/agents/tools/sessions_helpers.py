"""Sessions helpers — ported from bk/src/agents/tools/sessions-helpers.ts."""
from __future__ import annotations

from typing import Any


def format_session_summary(session: dict[str, Any]) -> str:
    sid = session.get("id", "unknown")[:8]
    status = session.get("status", "unknown")
    model = session.get("model", "unknown")
    return f"[{sid}] {status} ({model})"


def format_sessions_list(sessions: list[dict[str, Any]]) -> str:
    if not sessions:
        return "No sessions found."
    return "\n".join(format_session_summary(s) for s in sessions)
