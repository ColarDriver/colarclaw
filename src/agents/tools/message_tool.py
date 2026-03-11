"""Message tool — ported from bk/src/agents/tools/message-tool.ts."""
from __future__ import annotations

from typing import Any

MESSAGE_TOOL_NAME = "message"
MESSAGE_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "target": {"type": "string", "description": "Channel target (e.g. telegram:chatId)"},
        "content": {"type": "string", "description": "Message content"},
        "reply_to": {"type": "string", "description": "Message ID to reply to"},
        "media": {"type": "array", "items": {"type": "string"}, "description": "Media file paths"},
    },
    "required": ["content"],
}


async def handle_message_tool(params: dict[str, Any]) -> dict[str, Any]:
    target = params.get("target", "")
    content = params.get("content", "")
    return {"status": "ok", "target": target, "content_length": len(content)}
