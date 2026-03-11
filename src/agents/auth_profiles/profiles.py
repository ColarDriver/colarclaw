"""Auth profile profiles — ported from bk/src/agents/auth-profiles/profiles.ts.

Profile listing, upsert, and provider matching.
"""
from __future__ import annotations

import json
from typing import Any

from .types import AuthProfileCredential, AuthProfileStore


def dedupe_profile_ids(profile_ids: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for pid in profile_ids:
        if pid not in seen:
            seen.add(pid)
            result.append(pid)
    return result


def list_profiles_for_provider(store: AuthProfileStore, provider: str) -> list[str]:
    from ..model_selection import normalize_provider_id
    provider_key = normalize_provider_id(provider)
    return [
        pid for pid, cred in store.profiles.items()
        if normalize_provider_id(getattr(cred, "provider", "")) == provider_key
    ]


def upsert_auth_profile(
    store: AuthProfileStore,
    profile_id: str,
    credential: AuthProfileCredential,
) -> None:
    store.profiles[profile_id] = credential


def mark_auth_profile_good(
    store: AuthProfileStore,
    provider: str,
    profile_id: str,
) -> None:
    profile = store.profiles.get(profile_id)
    if not profile or getattr(profile, "provider", "") != provider:
        return
    if store.last_good is None:
        store.last_good = {}
    store.last_good[provider] = profile_id
