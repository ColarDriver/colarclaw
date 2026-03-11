"""Session status tool — ported from bk/src/agents/tools/session-status-tool.ts."""
from __future__ import annotations

from typing import Any

SESSION_STATUS_TOOL_NAME = "session_status"
SESSION_STATUS_SCHEMA = {
    "type": "object",
    "properties": {
        "session_id": {"type": "string"},
        "include_history": {"type": "boolean"},
    },
}


async def handle_session_status_tool(params: dict[str, Any]) -> dict[str, Any]:
    session_id = params.get("session_id", "")
    return {"status": "active", "session_id": session_id}
