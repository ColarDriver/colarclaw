"""Schema typebox — ported from bk/src/agents/schema/typebox.ts.

Schema helpers for tool input validation. Python equivalent of TypeBox
helpers using plain dicts.
"""
from __future__ import annotations

from typing import Any


def string_enum(values: list[str], description: str | None = None, title: str | None = None, default: str | None = None) -> dict[str, Any]:
    """Create a string enum schema (safe for all providers)."""
    schema: dict[str, Any] = {"type": "string", "enum": list(values)}
    if description:
        schema["description"] = description
    if title:
        schema["title"] = title
    if default:
        schema["default"] = default
    return schema


def optional_string_enum(values: list[str], **kwargs: Any) -> dict[str, Any]:
    """Create an optional string enum schema."""
    return string_enum(values, **kwargs)


def channel_target_schema(description: str | None = None) -> dict[str, Any]:
    """Schema for a channel target string."""
    return {
        "type": "string",
        "description": description or "Channel target identifier (e.g. 'telegram:chatId')",
    }


def channel_targets_schema(description: str | None = None) -> dict[str, Any]:
    """Schema for an array of channel targets."""
    return {
        "type": "array",
        "items": channel_target_schema(description),
    }
