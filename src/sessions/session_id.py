"""Session ID — ported from bk/src/sessions/session-id.ts."""
from __future__ import annotations
import re

SESSION_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

def looks_like_session_id(value: str) -> bool:
    return bool(SESSION_ID_RE.match(value.strip()))
