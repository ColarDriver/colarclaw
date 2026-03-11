"""Auth profile display — ported from bk/src/agents/auth-profiles/display.ts."""
from __future__ import annotations

from typing import Any

from .types import AuthProfileStore


def resolve_auth_profile_display_label(
    store: AuthProfileStore,
    profile_id: str,
    cfg: Any | None = None,
) -> str:
    """Resolve a human-readable display label for an auth profile."""
    profile = store.profiles.get(profile_id)
    config_email = None
    if cfg and hasattr(cfg, "auth"):
        profiles_cfg = getattr(getattr(cfg, "auth", None), "profiles", None)
        if profiles_cfg and isinstance(profiles_cfg, dict):
            profile_cfg = profiles_cfg.get(profile_id)
            if profile_cfg and isinstance(profile_cfg, dict):
                config_email = (profile_cfg.get("email") or "").strip() or None

    email = config_email
    if not email and profile:
        email = (getattr(profile, "email", None) or "").strip() or None

    if email:
        return f"{profile_id} ({email})"
    return profile_id
