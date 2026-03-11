"""Tool mutation — ported from bk/src/agents/tool-mutation.ts."""
from __future__ import annotations
from typing import Any

def add_tool_metadata(tool: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    existing = tool.get("metadata", {})
    return {**tool, "metadata": {**existing, **metadata}}

def set_tool_description(tool: dict[str, Any], description: str) -> dict[str, Any]:
    return {**tool, "description": description}

def rename_tool(tool: dict[str, Any], name: str) -> dict[str, Any]:
    return {**tool, "name": name}

def filter_tools_by_name(tools: list[dict[str, Any]], allowed: set[str]) -> list[dict[str, Any]]:
    lower_allowed = {n.lower() for n in allowed}
    return [t for t in tools if t.get("name", "").lower() in lower_allowed]

def exclude_tools_by_name(tools: list[dict[str, Any]], excluded: set[str]) -> list[dict[str, Any]]:
    lower_excluded = {n.lower() for n in excluded}
    return [t for t in tools if t.get("name", "").lower() not in lower_excluded]
