"""Schema clean for xAI — ported from bk/src/agents/schema/clean-for-xai.ts.

Cleans tool schemas for xAI (Grok) API compatibility.
"""
from __future__ import annotations

import copy
from typing import Any


def clean_schema_for_xai(schema: dict[str, Any]) -> dict[str, Any]:
    """Clean a JSON schema for xAI API compatibility.

    xAI has specific schema requirements similar to OpenAI.
    """
    cleaned = copy.deepcopy(schema)
    _clean_node(cleaned)
    return cleaned


def _clean_node(node: dict[str, Any]) -> None:
    # Remove unsupported keywords
    for key in ["$ref", "$schema", "examples"]:
        node.pop(key, None)

    # Ensure type is present
    if "type" not in node and "properties" in node:
        node["type"] = "object"

    if "properties" in node and isinstance(node["properties"], dict):
        for prop in node["properties"].values():
            if isinstance(prop, dict):
                _clean_node(prop)

    if "items" in node and isinstance(node["items"], dict):
        _clean_node(node["items"])
