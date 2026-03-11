"""Schema clean for Gemini — ported from bk/src/agents/schema/clean-for-gemini.ts.

Cleans tool schemas for Gemini API compatibility.
"""
from __future__ import annotations

import copy
from typing import Any


def clean_schema_for_gemini(schema: dict[str, Any]) -> dict[str, Any]:
    """Clean a JSON schema for Gemini API compatibility.

    Gemini has stricter schema requirements:
    - No 'additionalProperties'
    - No 'anyOf', 'oneOf', 'allOf'
    - Must have explicit 'type'
    """
    cleaned = copy.deepcopy(schema)
    _clean_node(cleaned)
    return cleaned


def _clean_node(node: dict[str, Any]) -> None:
    # Remove unsupported keywords
    for key in ["additionalProperties", "anyOf", "oneOf", "allOf", "$ref", "$schema"]:
        node.pop(key, None)

    # Ensure type is present
    if "type" not in node and "properties" in node:
        node["type"] = "object"

    # Recursively clean nested schemas
    if "properties" in node and isinstance(node["properties"], dict):
        for prop in node["properties"].values():
            if isinstance(prop, dict):
                _clean_node(prop)

    if "items" in node and isinstance(node["items"], dict):
        _clean_node(node["items"])
