"""Memory tool — ported from bk/src/agents/tools/memory-tool.ts."""
from __future__ import annotations

from typing import Any

MEMORY_TOOL_NAME = "memory"
MEMORY_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["store", "recall", "search", "list", "delete"]},
        "key": {"type": "string"},
        "value": {"type": "string"},
        "query": {"type": "string"},
    },
    "required": ["action"],
}


async def handle_memory_tool(params: dict[str, Any]) -> dict[str, Any]:
    action = params.get("action", "")
    return {"status": "ok", "action": action}


def format_memory_citations(results: list[dict[str, Any]]) -> str:
    if not results:
        return "No relevant memories found."
    lines = []
    for i, r in enumerate(results, 1):
        key = r.get("key", "")
        snippet = (r.get("value", ""))[:100]
        lines.append(f"{i}. [{key}] {snippet}")
    return "\n".join(lines)
