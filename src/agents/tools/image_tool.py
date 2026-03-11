"""Image tool — ported from bk/src/agents/tools/image-tool.ts."""
from __future__ import annotations

from typing import Any

IMAGE_TOOL_NAME = "image"
IMAGE_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["generate", "edit", "describe"]},
        "prompt": {"type": "string", "description": "Prompt for image generation"},
        "image_path": {"type": "string", "description": "Path to image file"},
        "model": {"type": "string", "description": "Model to use"},
    },
    "required": ["action"],
}


async def handle_image_tool(params: dict[str, Any]) -> dict[str, Any]:
    action = params.get("action", "")
    return {"status": "ok", "action": action}
