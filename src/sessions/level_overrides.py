"""Level overrides — ported from bk/src/sessions/level-overrides.ts.

Verbose level parsing and application for session entries.
"""
from __future__ import annotations

from typing import Any, Literal

VerboseLevel = Literal["on", "off"]

_VERBOSE_MAP = {"on": "on", "off": "off", "true": "on", "false": "off", "1": "on", "0": "off"}


def normalize_verbose_level(raw: str | None) -> VerboseLevel | None:
    if not raw:
        return None
    return _VERBOSE_MAP.get(raw.strip().lower())


def parse_verbose_override(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {"ok": True, "value": None}
    if not isinstance(raw, str):
        return {"ok": False, "error": 'invalid verboseLevel (use "on"|"off")'}
    normalized = normalize_verbose_level(raw)
    if not normalized:
        return {"ok": False, "error": 'invalid verboseLevel (use "on"|"off")'}
    return {"ok": True, "value": normalized}


def apply_verbose_override(entry: dict[str, Any], level: str | None) -> None:
    if level is None:
        entry.pop("verboseLevel", None)
    else:
        entry["verboseLevel"] = level
