"""Channels allow_from — ported from bk/src/channels/allow-from.ts,
allowlist-match.ts, allowlists/resolve-utils.ts.

Allowlist resolution, merging, and sender-matching utilities.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ─── allow-from.ts ───

def merge_dm_allow_from_sources(
    allow_from: list[str | int] | None = None,
    store_allow_from: list[str | int] | None = None,
    dm_policy: str | None = None,
) -> list[str]:
    """Merge DM allowFrom entries from config and store."""
    store_entries = [] if dm_policy == "allowlist" else (store_allow_from or [])
    combined = list(allow_from or []) + list(store_entries)
    return [s for s in (str(v).strip() for v in combined) if s]


def resolve_group_allow_from_sources(
    allow_from: list[str | int] | None = None,
    group_allow_from: list[str | int] | None = None,
    fallback_to_allow_from: bool = True,
) -> list[str]:
    """Resolve group allowFrom entries with optional fallback."""
    explicit = None
    if group_allow_from and len(group_allow_from) > 0:
        explicit = group_allow_from
    if explicit:
        scoped = explicit
    elif not fallback_to_allow_from:
        scoped = []
    else:
        scoped = allow_from or []
    return [s for s in (str(v).strip() for v in scoped) if s]


def first_defined(*values: Any) -> Any:
    """Return the first defined (non-None) value."""
    for v in values:
        if v is not None:
            return v
    return None


def is_sender_id_allowed(
    entries: list[str],
    has_wildcard: bool,
    has_entries: bool,
    sender_id: str | None,
    allow_when_empty: bool = True,
) -> bool:
    """Check if a sender ID is allowed by the allowlist."""
    if not has_entries:
        return allow_when_empty
    if has_wildcard:
        return True
    if not sender_id:
        return False
    return sender_id in entries


# ─── allowlist-match.ts ───

@dataclass
class AllowlistMatchResult:
    allowed: bool = False
    matched_entry: str | None = None
    has_entries: bool = False
    has_wildcard: bool = False


def match_allowlist(
    entries: list[str],
    sender_id: str | None,
    normalize_fn: Any = None,
) -> AllowlistMatchResult:
    """Match a sender against an allowlist."""
    if not entries:
        return AllowlistMatchResult(allowed=True, has_entries=False)

    has_wildcard = "*" in entries
    has_entries = len(entries) > 0

    if has_wildcard:
        return AllowlistMatchResult(
            allowed=True, has_entries=True, has_wildcard=True,
        )
    if not sender_id:
        return AllowlistMatchResult(allowed=False, has_entries=True)

    normalized_sender = normalize_fn(sender_id) if normalize_fn else sender_id.strip().lower()
    for entry in entries:
        normalized_entry = normalize_fn(entry) if normalize_fn else entry.strip().lower()
        if normalized_entry == normalized_sender:
            return AllowlistMatchResult(
                allowed=True, matched_entry=entry, has_entries=True,
            )

    return AllowlistMatchResult(allowed=False, has_entries=True)


# ─── allowlists/resolve-utils.ts ───

def resolve_allow_from_entries(
    raw_allow_from: list[str | int] | None,
) -> list[str]:
    """Normalize raw allowFrom config entries to trimmed strings."""
    if not raw_allow_from:
        return []
    return [s for s in (str(v).strip() for v in raw_allow_from) if s]


def resolve_allowlist_with_wildcard(
    entries: list[str],
) -> tuple[list[str], bool]:
    """Split entries into (non-wildcard entries, has_wildcard)."""
    has_wildcard = "*" in entries
    filtered = [e for e in entries if e != "*"]
    return filtered, has_wildcard


def format_allow_from_lowercase(
    allow_from: list[str | int],
    strip_prefix_re: re.Pattern[str] | None = None,
) -> list[str]:
    """Format allowFrom entries: lowercase, optional prefix stripping."""
    result = []
    for entry in allow_from:
        s = str(entry).strip()
        if strip_prefix_re:
            s = strip_prefix_re.sub("", s)
        s = s.strip().lower()
        if s:
            result.append(s)
    return result


def map_allow_from_entries(
    raw: list[str | int] | None,
) -> list[str]:
    """Map raw allowFrom config to normalized string list."""
    if not raw:
        return []
    return [str(v).strip() for v in raw if str(v).strip()]
