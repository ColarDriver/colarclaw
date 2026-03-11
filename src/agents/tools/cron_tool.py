"""Cron tool — ported from bk/src/agents/tools/cron-tool.ts."""
from __future__ import annotations

from typing import Any

CRON_TOOL_NAME = "cron"
CRON_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["create", "list", "delete", "pause", "resume"]},
        "schedule": {"type": "string", "description": "Cron expression"},
        "task": {"type": "string", "description": "Task to execute"},
        "cron_id": {"type": "string", "description": "Cron job ID"},
    },
    "required": ["action"],
}


async def handle_cron_tool(params: dict[str, Any]) -> dict[str, Any]:
    action = params.get("action", "")
    return {"status": "ok", "action": action}
