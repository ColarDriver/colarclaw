"""Auth profile session override — ported from bk/src/agents/auth-profiles/session-override.ts.

Per-session auth profile overrides.
"""
from __future__ import annotations

from typing import Any

from .types import AuthProfileStore


def resolve_session_auth_override(
    store: AuthProfileStore,
    session_id: str | None = None,
    provider: str | None = None,
    override_profile_id: str | None = None,
) -> str | None:
    """Resolve a per-session auth profile override."""
    if not override_profile_id:
        return None
    if override_profile_id not in store.profiles:
        return None
    if provider:
        from ..model_selection import normalize_provider_id
        cred = store.profiles[override_profile_id]
        cred_provider = normalize_provider_id(getattr(cred, "provider", ""))
        if cred_provider != normalize_provider_id(provider):
            return None
    return override_profile_id
