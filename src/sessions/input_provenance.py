"""Input provenance — ported from bk/src/sessions/input-provenance.ts.

Track the origin of user messages (external, inter-session, system).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

InputProvenanceKind = Literal["external_user", "inter_session", "internal_system"]

INPUT_PROVENANCE_KIND_VALUES = ("external_user", "inter_session", "internal_system")


@dataclass
class InputProvenance:
    kind: InputProvenanceKind
    source_session_key: str | None = None
    source_channel: str | None = None
    source_tool: str | None = None


def _normalize_optional_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed or None


def normalize_input_provenance(value: Any) -> InputProvenance | None:
    """Normalize a raw provenance value to InputProvenance."""
    if not value or not isinstance(value, dict):
        return None
    kind = value.get("kind")
    if kind not in INPUT_PROVENANCE_KIND_VALUES:
        return None
    return InputProvenance(
        kind=kind,
        source_session_key=_normalize_optional_string(value.get("sourceSessionKey")),
        source_channel=_normalize_optional_string(value.get("sourceChannel")),
        source_tool=_normalize_optional_string(value.get("sourceTool")),
    )


def apply_input_provenance_to_user_message(
    message: dict[str, Any],
    provenance: InputProvenance | None,
) -> dict[str, Any]:
    """Apply input provenance to a user message."""
    if not provenance or message.get("role") != "user":
        return message
    existing = normalize_input_provenance(message.get("provenance"))
    if existing:
        return message
    return {**message, "provenance": {
        "kind": provenance.kind,
        "sourceSessionKey": provenance.source_session_key,
        "sourceChannel": provenance.source_channel,
        "sourceTool": provenance.source_tool,
    }}


def is_inter_session_input_provenance(value: Any) -> bool:
    p = normalize_input_provenance(value)
    return p is not None and p.kind == "inter_session"


def has_inter_session_user_provenance(message: dict[str, Any] | None) -> bool:
    if not message or message.get("role") != "user":
        return False
    return is_inter_session_input_provenance(message.get("provenance"))
