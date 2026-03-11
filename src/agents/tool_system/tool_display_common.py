"""Tool display common — ported from bk/src/agents/tool-display-common.ts.

Common tool display helpers for formatting tool call results.
"""
from __future__ import annotations

import json
from typing import Any


def format_tool_result_summary(
    tool_name: str,
    result: Any,
    max_length: int = 200,
) -> str:
    """Format a tool result into a concise summary string."""
    if result is None:
        return f"{tool_name}: (no result)"

    if isinstance(result, str):
        text = result.strip()
    elif isinstance(result, dict):
        # Try to extract text from content blocks
        text = _extract_text_from_result(result)
    else:
        text = str(result)

    if not text:
        return f"{tool_name}: (empty)"

    if len(text) > max_length:
        return f"{tool_name}: {text[:max_length - 3]}..."
    return f"{tool_name}: {text}"


def format_tool_error_summary(
    tool_name: str,
    error: Any,
    max_length: int = 200,
) -> str:
    """Format a tool error into a summary string."""
    if isinstance(error, Exception):
        msg = str(error) or type(error).__name__
    elif isinstance(error, str):
        msg = error
    else:
        msg = str(error) if error else "Unknown error"

    if len(msg) > max_length:
        msg = msg[: max_length - 3] + "..."
    return f"{tool_name} ERROR: {msg}"


def _extract_text_from_result(result: dict[str, Any]) -> str:
    """Extract text content from a structured tool result."""
    content = result.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text", "")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        return "\n".join(parts)
    # Try direct text field
    text = result.get("text") or result.get("output") or result.get("message")
    if isinstance(text, str):
        return text.strip()
    return ""


def format_tool_call_display(
    tool_name: str,
    params: Any = None,
    max_params_length: int = 100,
) -> str:
    """Format a tool call for display."""
    if params is None:
        return f"{tool_name}()"

    if isinstance(params, dict):
        try:
            params_str = json.dumps(params, ensure_ascii=False)
        except Exception:
            params_str = str(params)
    else:
        params_str = str(params)

    if len(params_str) > max_params_length:
        params_str = params_str[: max_params_length - 3] + "..."

    return f"{tool_name}({params_str})"
