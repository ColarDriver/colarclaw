"""Tool summaries — ported from bk/src/agents/tool-summaries.ts."""
from __future__ import annotations
from typing import Any

def summarize_tool_calls(messages: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") in ("toolCall", "toolUse", "functionCall"):
                name = block.get("name", "unknown")
                counts[name] = counts.get(name, 0) + 1
    return counts

def format_tool_usage_summary(counts: dict[str, int]) -> str:
    if not counts:
        return "No tools used"
    parts = [f"{name}×{count}" for name, count in sorted(counts.items(), key=lambda x: -x[1])]
    return ", ".join(parts)
