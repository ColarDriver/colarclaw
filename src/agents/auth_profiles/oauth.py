"""Auth profile OAuth — ported from bk/src/agents/auth-profiles/oauth.ts.

OAuth token refresh and management for auth profiles.
"""
from __future__ import annotations

import time
from typing import Any

from .constants import log
from .store import save_auth_profile_store
from .types import AuthProfileStore, OAuthCredential


async def refresh_oauth_profile(
    store: AuthProfileStore,
    profile_id: str,
    agent_dir: str | None = None,
) -> bool:
    """Attempt to refresh an OAuth profile's tokens."""
    profile = store.profiles.get(profile_id)
    if not profile or not isinstance(profile, OAuthCredential):
        return False
    if not profile.refresh:
        log.debug("No refresh token for %s", profile_id)
        return False

    # Provider-specific refresh logic would go here
    # For now, this is a placeholder for the refresh mechanism
    log.debug("OAuth refresh for %s (provider: %s)", profile_id, profile.provider)
    return False


def is_oauth_token_near_expiry(
    profile: OAuthCredential,
    threshold_ms: float = 5 * 60 * 1000,
) -> bool:
    """Check if an OAuth token is near expiry."""
    if not profile.expires:
        return False
    now = time.time() * 1000
    return now >= (profile.expires - threshold_ms)


def should_refresh_oauth_profile(
    store: AuthProfileStore,
    profile_id: str,
    threshold_ms: float = 5 * 60 * 1000,
) -> bool:
    """Check if an OAuth profile should be refreshed."""
    profile = store.profiles.get(profile_id)
    if not profile or not isinstance(profile, OAuthCredential):
        return False
    if not profile.refresh:
        return False
    return is_oauth_token_near_expiry(profile, threshold_ms)
