"""Gateway tool — ported from bk/src/agents/tools/gateway-tool.ts + gateway.ts."""
from __future__ import annotations

from typing import Any

GATEWAY_TOOL_NAME = "gateway"
GATEWAY_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["status", "restart", "config"]},
        "config_key": {"type": "string"},
        "config_value": {"type": "string"},
    },
    "required": ["action"],
}


async def handle_gateway_tool(params: dict[str, Any]) -> dict[str, Any]:
    action = params.get("action", "")
    return {"status": "ok", "action": action}


def resolve_gateway_endpoint(base_url: str | None = None) -> str:
    return base_url or "http://localhost:18789"
