"""Sessions spawn tool — ported from bk/src/agents/tools/sessions-spawn.ts."""
from __future__ import annotations

from typing import Any

SESSIONS_SPAWN_TOOL_NAME = "sessions_spawn"
SESSIONS_SPAWN_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Subagent name"},
        "message": {"type": "string", "description": "Initial message"},
        "model": {"type": "string", "description": "Model to use"},
        "provider": {"type": "string", "description": "Provider to use"},
    },
    "required": ["name", "message"],
}


async def handle_sessions_spawn(params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name", "")
    message = params.get("message", "")
    return {"status": "spawned", "name": name}
