"""Nodes tool — ported from bk/src/agents/tools/nodes-tool.ts + nodes-utils.ts."""
from __future__ import annotations

from typing import Any

NODES_TOOL_NAME = "nodes"
NODES_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["list", "get", "create", "update", "delete"]},
        "node_id": {"type": "string"},
        "content": {"type": "string"},
        "metadata": {"type": "object"},
    },
    "required": ["action"],
}


async def handle_nodes_tool(params: dict[str, Any]) -> dict[str, Any]:
    action = params.get("action", "")
    return {"status": "ok", "action": action}


def format_node_display(node: dict[str, Any]) -> str:
    node_id = node.get("id", "unknown")
    name = node.get("name", node_id)
    return f"[{node_id}] {name}"
