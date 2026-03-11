"""Stable JSON stringify — ported from bk/src/agents/stable-stringify.ts."""
from __future__ import annotations
import json
from typing import Any

def stable_stringify(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return json.dumps(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ",".join(stable_stringify(entry) for entry in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value.keys())
        entries = [f"{json.dumps(k)}:{stable_stringify(value[k])}" for k in keys]
        return "{" + ",".join(entries) + "}"
    return json.dumps(str(value))
