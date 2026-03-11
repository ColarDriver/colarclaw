"""Identity avatar — ported from bk/src/agents/identity-avatar.ts."""
from __future__ import annotations
import os
import re

DATA_URI_RE = re.compile(r"^data:", re.IGNORECASE)
HTTP_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

def resolve_avatar_source(
    avatar: str | None, workspace_dir: str | None = None,
) -> str | None:
    if not avatar or not isinstance(avatar, str):
        return None
    trimmed = avatar.strip()
    if not trimmed:
        return None
    if DATA_URI_RE.match(trimmed) or HTTP_URL_RE.match(trimmed):
        return trimmed
    if workspace_dir:
        resolved = os.path.join(workspace_dir, trimmed)
        if os.path.isfile(resolved):
            return resolved
    return None

def is_avatar_url(avatar: str | None) -> bool:
    if not avatar:
        return False
    return bool(HTTP_URL_RE.match(avatar.strip()))

def is_avatar_data_uri(avatar: str | None) -> bool:
    if not avatar:
        return False
    return bool(DATA_URI_RE.match(avatar.strip()))
