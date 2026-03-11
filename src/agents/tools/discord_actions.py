"""Discord actions — ported from bk/src/agents/tools/discord-actions.ts."""
from __future__ import annotations

from typing import Any

DISCORD_ACTIONS_TOOL_NAME = "discord_actions"
DISCORD_ACTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": [
            "send_message", "react", "pin", "delete",
            "create_thread", "list_channels", "set_presence",
        ]},
        "channel_id": {"type": "string"},
        "message_id": {"type": "string"},
        "content": {"type": "string"},
        "emoji": {"type": "string"},
    },
    "required": ["action"],
}


async def handle_discord_actions(params: dict[str, Any]) -> dict[str, Any]:
    action = params.get("action", "")
    return {"status": "ok", "action": action}
