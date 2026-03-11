"""Session slug — ported from bk/src/agents/session-slug.ts."""
from __future__ import annotations
import hashlib
import re

SLUG_MAX_LEN = 60
SLUG_SANITIZE_RE = re.compile(r"[^a-z0-9_-]")

def session_key_to_slug(session_key: str) -> str:
    if not session_key:
        return "default"
    lower = session_key.strip().lower()
    sanitized = SLUG_SANITIZE_RE.sub("-", lower)
    sanitized = re.sub(r"-{2,}", "-", sanitized).strip("-")
    if not sanitized:
        return hashlib.sha256(session_key.encode()).hexdigest()[:12]
    if len(sanitized) > SLUG_MAX_LEN:
        suffix = hashlib.sha256(session_key.encode()).hexdigest()[:8]
        sanitized = sanitized[:SLUG_MAX_LEN - 9] + "-" + suffix
    return sanitized

def slug_to_session_key(slug: str) -> str:
    return slug
