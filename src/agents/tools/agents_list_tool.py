"""Agents list tool — ported from bk/src/agents/tools/agents-list-tool.ts."""
from __future__ import annotations

from typing import Any

AGENTS_LIST_TOOL_NAME = "agents_list"
AGENTS_LIST_SCHEMA = {
    "type": "object",
    "properties": {
        "status_filter": {
            "type": "string",
            "description": "Filter agents by status (active, idle, all)",
            "enum": ["active", "idle", "all"],
        },
    },
}


async def handle_agents_list(params: dict[str, Any]) -> str:
    """List available agents."""
    return "No agents currently registered."
