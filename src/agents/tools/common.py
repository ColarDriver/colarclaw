"""Tools common — ported from bk/src/agents/tools/common.ts.

Shared tool utilities: parameter parsing, error formatting.
"""
from __future__ import annotations

from typing import Any


def parse_tool_params(params: dict[str, Any] | str | None) -> dict[str, Any]:
    """Parse tool call parameters, handling string or dict input."""
    if params is None:
        return {}
    if isinstance(params, str):
        import json
        try:
            return json.loads(params)
        except (json.JSONDecodeError, ValueError):
            return {"raw": params}
    return dict(params)


def format_tool_error(tool_name: str, error: str | Exception) -> str:
    return f"Tool '{tool_name}' failed: {error}"


def format_tool_result(content: str, is_error: bool = False) -> dict[str, Any]:
    return {
        "type": "tool_result",
        "content": content,
        "is_error": is_error,
    }


def truncate_tool_output(output: str, max_chars: int = 50_000) -> str:
    if len(output) <= max_chars:
        return output
    half = (max_chars - 50) // 2
    return output[:half] + "\n... (output truncated) ...\n" + output[-half:]
