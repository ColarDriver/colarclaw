"""Tool display — ported from bk/src/agents/tool-display.ts + tool-display-common.ts.

Formats tool calls and results for human-readable display.
"""
from __future__ import annotations
import json
from typing import Any

MAX_DISPLAY_CONTENT_LENGTH = 500
MAX_INPUT_DISPLAY_LENGTH = 200

def format_tool_call_for_display(name: str, input_data: Any = None, tool_id: str | None = None) -> str:
    parts = [f"🔧 {name}"]
    if tool_id:
        parts.append(f"[{tool_id[:12]}]")
    if input_data is not None:
        if isinstance(input_data, dict):
            preview = json.dumps(input_data, ensure_ascii=False)
            if len(preview) > MAX_INPUT_DISPLAY_LENGTH:
                preview = preview[:MAX_INPUT_DISPLAY_LENGTH] + "…"
            parts.append(f"({preview})")
        elif isinstance(input_data, str):
            preview = input_data[:MAX_INPUT_DISPLAY_LENGTH]
            if len(input_data) > MAX_INPUT_DISPLAY_LENGTH:
                preview += "…"
            parts.append(f"({preview})")
    return " ".join(parts)

def format_tool_result_for_display(
    name: str, content: Any, is_error: bool = False, tool_id: str | None = None,
) -> str:
    status = "❌" if is_error else "✅"
    parts = [f"{status} {name}"]
    if tool_id:
        parts.append(f"[{tool_id[:12]}]")
    if content is not None:
        if isinstance(content, str):
            preview = content[:MAX_DISPLAY_CONTENT_LENGTH]
            if len(content) > MAX_DISPLAY_CONTENT_LENGTH:
                preview += "…"
            parts.append(f": {preview}")
        elif isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(str(block.get("text", "")))
            text = "\n".join(text_parts)
            if text:
                preview = text[:MAX_DISPLAY_CONTENT_LENGTH]
                if len(text) > MAX_DISPLAY_CONTENT_LENGTH:
                    preview += "…"
                parts.append(f": {preview}")
    return " ".join(parts)

def format_tool_summary(calls: list[dict[str, Any]]) -> str:
    if not calls:
        return "No tool calls"
    names = [c.get("name", "unknown") for c in calls]
    unique = list(dict.fromkeys(names))
    return f"{len(calls)} tool call(s): {', '.join(unique)}"
