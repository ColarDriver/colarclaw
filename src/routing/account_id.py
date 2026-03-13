"""Account ID normalization — ported from bk/src/routing/account-id.ts.

Canonical account ID normalization with LRU cache.
"""
from __future__ import annotations

import re
from collections import OrderedDict

DEFAULT_ACCOUNT_ID = "default"

_VALID_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$", re.IGNORECASE)
_INVALID_CHARS_RE = re.compile(r"[^a-z0-9_-]+")
_LEADING_DASH_RE = re.compile(r"^-+")
_TRAILING_DASH_RE = re.compile(r"-+$")
_CACHE_MAX = 512

# Blocked prototype keys (simplified)
_BLOCKED_KEYS = frozenset({
    "__proto__", "constructor", "prototype", "toString",
    "valueOf", "hasOwnProperty", "isPrototypeOf",
})

_normalize_cache: OrderedDict[str, str] = OrderedDict()
_normalize_optional_cache: OrderedDict[str, str | None] = OrderedDict()


def _canonicalize_account_id(value: str) -> str:
    if _VALID_ID_RE.match(value):
        return value.lower()
    result = value.lower()
    result = _INVALID_CHARS_RE.sub("-", result)
    result = _LEADING_DASH_RE.sub("", result)
    result = _TRAILING_DASH_RE.sub("", result)
    return result[:64]


def normalize_account_id(value: str | None = None) -> str:
    """Normalize an account ID, defaulting to 'default'."""
    trimmed = (value or "").strip()
    if not trimmed:
        return DEFAULT_ACCOUNT_ID

    cached = _normalize_cache.get(trimmed)
    if cached is not None:
        return cached

    canonical = _canonicalize_account_id(trimmed)
    if not canonical or canonical in _BLOCKED_KEYS:
        canonical = DEFAULT_ACCOUNT_ID

    _normalize_cache[trimmed] = canonical
    if len(_normalize_cache) > _CACHE_MAX:
        _normalize_cache.popitem(last=False)

    return canonical


def normalize_optional_account_id(value: str | None = None) -> str | None:
    """Normalize an account ID, returning None if empty."""
    trimmed = (value or "").strip()
    if not trimmed:
        return None

    if trimmed in _normalize_optional_cache:
        return _normalize_optional_cache[trimmed]

    canonical = _canonicalize_account_id(trimmed)
    result = canonical if canonical and canonical not in _BLOCKED_KEYS else None

    _normalize_optional_cache[trimmed] = result
    if len(_normalize_optional_cache) > _CACHE_MAX:
        _normalize_optional_cache.popitem(last=False)

    return result
