"""Web search tool — ported from bk/src/agents/tools/web-search-tool.ts."""
from __future__ import annotations

from typing import Any

WEB_SEARCH_TOOL_NAME = "web_search"
WEB_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Search query"},
        "max_results": {"type": "integer", "description": "Maximum results", "default": 5},
        "domain": {"type": "string", "description": "Restrict to domain"},
    },
    "required": ["query"],
}


async def handle_web_search(params: dict[str, Any]) -> dict[str, Any]:
    query = params.get("query", "")
    return {"status": "ok", "query": query, "results": []}
