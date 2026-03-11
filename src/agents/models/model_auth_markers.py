"""Model auth markers — ported from bk/src/agents/model-auth-markers.ts."""
from __future__ import annotations
import re

MARKER_PREFIX = "openclaw-auth:"

def encode_auth_marker(provider: str, profile_id: str | None = None) -> str:
    parts = [MARKER_PREFIX, provider.strip().lower()]
    if profile_id:
        parts.append(f":{profile_id.strip()}")
    return "".join(parts)

def decode_auth_marker(marker: str) -> dict[str, str] | None:
    if not marker.startswith(MARKER_PREFIX):
        return None
    rest = marker[len(MARKER_PREFIX):]
    parts = rest.split(":", 1)
    provider = parts[0].strip()
    if not provider:
        return None
    profile_id = parts[1].strip() if len(parts) > 1 else None
    return {"provider": provider, "profileId": profile_id} if profile_id else {"provider": provider}
