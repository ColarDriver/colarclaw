"""ACP meta — ported from bk/src/acp/meta.ts.

Utility functions for reading typed values from metadata dicts.
"""
from __future__ import annotations

from typing import Any


def read_string(meta: dict[str, Any] | None, keys: list[str]) -> str | None:
    if not meta:
        return None
    for key in keys:
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def read_bool(meta: dict[str, Any] | None, keys: list[str]) -> bool | None:
    if not meta:
        return None
    for key in keys:
        value = meta.get(key)
        if isinstance(value, bool):
            return value
    return None


def read_number(meta: dict[str, Any] | None, keys: list[str]) -> int | float | None:
    if not meta:
        return None
    for key in keys:
        value = meta.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
    return None
