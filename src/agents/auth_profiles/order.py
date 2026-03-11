"""Auth profile order — ported from bk/src/agents/auth-profiles/order.ts.

Profile ordering, eligibility, and round-robin rotation.
"""
from __future__ import annotations

import time
from typing import Any

from .credential_state import evaluate_stored_credential_eligibility
from .profiles import dedupe_profile_ids, list_profiles_for_provider
from .types import AuthProfileStore
from .usage import clear_expired_cooldowns, is_profile_in_cooldown, resolve_profile_unusable_until


def resolve_auth_profile_eligibility(
    store: AuthProfileStore,
    provider: str,
    profile_id: str,
    cfg: Any | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    from ..model_selection import normalize_provider_id
    provider_auth_key = normalize_provider_id(provider)
    cred = store.profiles.get(profile_id)
    if not cred:
        return {"eligible": False, "reason_code": "profile_missing"}
    if normalize_provider_id(getattr(cred, "provider", "")) != provider_auth_key:
        return {"eligible": False, "reason_code": "provider_mismatch"}
    result = evaluate_stored_credential_eligibility(cred, now)
    return {"eligible": result["eligible"], "reason_code": result["reason_code"]}


def resolve_auth_profile_order(
    store: AuthProfileStore,
    provider: str,
    preferred_profile: str | None = None,
    cfg: Any | None = None,
) -> list[str]:
    from ..model_selection import normalize_provider_id
    provider_key = normalize_provider_id(provider)
    now = time.time() * 1000

    clear_expired_cooldowns(store, now)
    base_order = list_profiles_for_provider(store, provider)
    if not base_order:
        return []

    def is_valid(pid: str) -> bool:
        result = resolve_auth_profile_eligibility(store, provider_key, pid, cfg, now)
        return result["eligible"]

    filtered = [pid for pid in base_order if is_valid(pid)]
    deduped = dedupe_profile_ids(filtered)

    # Sort: available profiles first, then cooldown-sorted
    available: list[str] = []
    in_cooldown: list[tuple[str, float]] = []
    for pid in deduped:
        if is_profile_in_cooldown(store, pid, now):
            stats = (store.usage_stats or {}).get(pid)
            until = resolve_profile_unusable_until(stats) if stats else now
            in_cooldown.append((pid, until or now))
        else:
            available.append(pid)

    # Sort available by type preference then lastUsed (round-robin)
    def sort_key(pid: str) -> tuple[int, float]:
        cred = store.profiles.get(pid)
        type_val = getattr(cred, "type", "") if cred else ""
        type_score = {"oauth": 0, "token": 1, "api_key": 2}.get(type_val, 3)
        stats = (store.usage_stats or {}).get(pid)
        last_used = stats.last_used if stats and stats.last_used else 0
        return (type_score, last_used)

    available.sort(key=sort_key)
    in_cooldown.sort(key=lambda x: x[1])
    ordered = available + [pid for pid, _ in in_cooldown]

    if preferred_profile and preferred_profile in ordered:
        return [preferred_profile] + [p for p in ordered if p != preferred_profile]
    return ordered
