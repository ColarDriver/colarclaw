"""Voice tool — ported from bk/src/agents/tools/voice-tool.ts."""
from __future__ import annotations

from typing import Any

VOICE_TOOL_NAME = "voice"
VOICE_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["speak", "transcribe", "listen"]},
        "text": {"type": "string", "description": "Text to speak"},
        "audio_path": {"type": "string", "description": "Audio file path"},
        "language": {"type": "string", "description": "Language code"},
    },
    "required": ["action"],
}


async def handle_voice_tool(params: dict[str, Any]) -> dict[str, Any]:
    action = params.get("action", "")
    return {"status": "ok", "action": action}
