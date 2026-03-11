"""Auth profile usage — ported from bk/src/agents/auth-profiles/usage.ts.

Usage stats tracking: round-robin, cooldowns, failure backoff.
"""
from __future__ import annotations

import math
import time
from typing import Any

from .constants import log
from .types import AuthProfileFailureReason, AuthProfileStore, ProfileUsageStats

FAILURE_REASON_PRIORITY: list[str] = [
    "auth_permanent", "auth", "billing", "format", "model_not_found",
    "overloaded", "timeout", "rate_limit", "unknown",
]
FAILURE_REASON_SET = set(FAILURE_REASON_PRIORITY)
FAILURE_REASON_ORDER = {r: i for i, r in enumerate(FAILURE_REASON_PRIORITY)}

_COOLDOWN_BYPASS_PROVIDERS = {"openrouter", "kilocode"}


def _is_cooldown_bypassed(provider: str | None) -> bool:
    from ..model_selection import normalize_provider_id
    return normalize_provider_id(provider or "") in _COOLDOWN_BYPASS_PROVIDERS


def resolve_profile_unusable_until(stats: ProfileUsageStats) -> float | None:
    values = [v for v in [stats.cooldown_until, stats.disabled_until]
              if isinstance(v, (int, float)) and v > 0]
    return max(values) if values else None


def is_profile_in_cooldown(store: AuthProfileStore, profile_id: str, now: float | None = None) -> bool:
    profile = store.profiles.get(profile_id)
    if profile and _is_cooldown_bypassed(getattr(profile, "provider", None)):
        return False
    stats = (store.usage_stats or {}).get(profile_id)
    if not stats:
        return False
    until = resolve_profile_unusable_until(stats)
    ts = now or time.time() * 1000
    return bool(until and ts < until)


def clear_expired_cooldowns(store: AuthProfileStore, now: float | None = None) -> bool:
    if not store.usage_stats:
        return False
    ts = now or time.time() * 1000
    mutated = False
    for profile_id, stats in list(store.usage_stats.items()):
        if not stats:
            continue
        profile_mutated = False
        if (isinstance(stats.cooldown_until, (int, float))
                and stats.cooldown_until > 0 and ts >= stats.cooldown_until):
            stats.cooldown_until = None
            profile_mutated = True
        if (isinstance(stats.disabled_until, (int, float))
                and stats.disabled_until > 0 and ts >= stats.disabled_until):
            stats.disabled_until = None
            stats.disabled_reason = None
            profile_mutated = True
        if profile_mutated and not resolve_profile_unusable_until(stats):
            stats.error_count = 0
            stats.failure_counts = None
        if profile_mutated:
            mutated = True
    return mutated


def calculate_auth_profile_cooldown_ms(error_count: int) -> float:
    normalized = max(1, error_count)
    return min(60 * 60 * 1000, 60 * 1000 * (5 ** min(normalized - 1, 3)))


def get_soonest_cooldown_expiry(store: AuthProfileStore, profile_ids: list[str]) -> float | None:
    soonest: float | None = None
    for pid in profile_ids:
        stats = (store.usage_stats or {}).get(pid)
        if not stats:
            continue
        until = resolve_profile_unusable_until(stats)
        if until is None or until <= 0:
            continue
        if soonest is None or until < soonest:
            soonest = until
    return soonest


def resolve_profiles_unavailable_reason(
    store: AuthProfileStore,
    profile_ids: list[str],
    now: float | None = None,
) -> str | None:
    ts = now or time.time() * 1000
    scores: dict[str, float] = {}
    for pid in profile_ids:
        stats = (store.usage_stats or {}).get(pid)
        if not stats:
            continue
        disabled_active = (isinstance(stats.disabled_until, (int, float))
                           and stats.disabled_until > 0 and ts < stats.disabled_until)
        if disabled_active and stats.disabled_reason and stats.disabled_reason in FAILURE_REASON_SET:
            scores[stats.disabled_reason] = scores.get(stats.disabled_reason, 0) + 1000
            continue
        cooldown_active = (isinstance(stats.cooldown_until, (int, float))
                           and stats.cooldown_until > 0 and ts < stats.cooldown_until)
        if not cooldown_active:
            continue
        recorded = False
        for reason, count in (stats.failure_counts or {}).items():
            if reason in FAILURE_REASON_SET and isinstance(count, (int, float)) and count > 0:
                scores[reason] = scores.get(reason, 0) + count
                recorded = True
        if not recorded:
            scores["rate_limit"] = scores.get("rate_limit", 0) + 1

    if not scores:
        return None
    best = None
    best_score = -1.0
    best_priority = 999
    for reason in FAILURE_REASON_PRIORITY:
        score = scores.get(reason, 0)
        if score <= 0:
            continue
        priority = FAILURE_REASON_ORDER.get(reason, 999)
        if score > best_score or (score == best_score and priority < best_priority):
            best = reason
            best_score = score
            best_priority = priority
    return best


def resolve_profile_unusable_until_for_display(
    store: AuthProfileStore,
    profile_id: str,
) -> float | None:
    profile = store.profiles.get(profile_id)
    if profile and _is_cooldown_bypassed(getattr(profile, "provider", None)):
        return None
    stats = (store.usage_stats or {}).get(profile_id)
    if not stats:
        return None
    return resolve_profile_unusable_until(stats)
