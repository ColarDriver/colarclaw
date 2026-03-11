"""Canvas tool — ported from bk/src/agents/tools/canvas-tool.ts."""
from __future__ import annotations

from typing import Any

CANVAS_TOOL_NAME = "canvas"
CANVAS_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["create", "update", "render"]},
        "content": {"type": "string"},
        "format": {"type": "string", "enum": ["html", "markdown", "svg"]},
    },
    "required": ["action"],
}


async def handle_canvas_tool(params: dict[str, Any]) -> dict[str, Any]:
    action = params.get("action", "")
    return {"status": "ok", "action": action}
