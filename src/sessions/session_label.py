"""Session label — ported from bk/src/sessions/session-label.ts."""
from __future__ import annotations
from dataclasses import dataclass

SESSION_LABEL_MAX_LENGTH = 64

@dataclass
class ParsedSessionLabel:
    ok: bool
    label: str = ""
    error: str = ""

def parse_session_label(raw: str | None) -> ParsedSessionLabel:
    if not isinstance(raw, str):
        return ParsedSessionLabel(ok=False, error="invalid label: must be a string")
    trimmed = raw.strip()
    if not trimmed:
        return ParsedSessionLabel(ok=False, error="invalid label: empty")
    if len(trimmed) > SESSION_LABEL_MAX_LENGTH:
        return ParsedSessionLabel(ok=False, error=f"invalid label: too long (max {SESSION_LABEL_MAX_LENGTH})")
    return ParsedSessionLabel(ok=True, label=trimmed)
