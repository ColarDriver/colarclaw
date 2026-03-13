"""Channels config — ported from bk/src/channels/channel-config.ts.

Channel configuration matching: entry resolution with direct/parent/wildcard
fallback, slug normalization, key candidate building, and nested allowlist decisions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Literal


# ─── types ───

ChannelMatchSource = Literal["direct", "parent", "wildcard"]


@dataclass
class ChannelEntryMatch:
    entry: Any = None
    key: str | None = None
    wildcard_entry: Any = None
    wildcard_key: str | None = None
    parent_entry: Any = None
    parent_key: str | None = None
    match_key: str | None = None
    match_source: ChannelMatchSource | None = None


# ─── slug normalization ───

def normalize_channel_slug(value: str) -> str:
    """Normalize a channel slug: lowercase, strip #, replace non-alnum with -."""
    cleaned = value.strip().lower()
    if cleaned.startswith("#"):
        cleaned = cleaned[1:]
    cleaned = re.sub(r"[^a-z0-9]+", "-", cleaned)
    cleaned = cleaned.strip("-")
    return cleaned


# ─── key candidates ───

def build_channel_key_candidates(*keys: str | None) -> list[str]:
    """Build deduplicated list of key candidates for channel entry matching."""
    seen: set[str] = set()
    candidates: list[str] = []
    for key in keys:
        if not isinstance(key, str):
            continue
        trimmed = key.strip()
        if not trimmed or trimmed in seen:
            continue
        seen.add(trimmed)
        candidates.append(trimmed)
    return candidates


# ─── entry matching ───

def resolve_channel_entry_match(
    entries: dict[str, Any] | None = None,
    keys: list[str] | None = None,
    wildcard_key: str | None = None,
) -> ChannelEntryMatch:
    """Resolve a channel entry from a dict by trying keys in order, with wildcard fallback."""
    entries = entries or {}
    keys = keys or []
    match = ChannelEntryMatch()

    for key in keys:
        if key in entries:
            match.entry = entries[key]
            match.key = key
            break

    if wildcard_key and wildcard_key in entries:
        match.wildcard_entry = entries[wildcard_key]
        match.wildcard_key = wildcard_key

    return match


def resolve_channel_entry_match_with_fallback(
    entries: dict[str, Any] | None = None,
    keys: list[str] | None = None,
    parent_keys: list[str] | None = None,
    wildcard_key: str | None = None,
    normalize_key: Callable[[str], str] | None = None,
) -> ChannelEntryMatch:
    """Resolve channel entry with direct → normalized → parent → wildcard fallback chain."""
    direct = resolve_channel_entry_match(entries, keys, wildcard_key)

    if direct.entry is not None and direct.key is not None:
        direct.match_key = direct.key
        direct.match_source = "direct"
        return direct

    # Try normalized keys
    if normalize_key and keys:
        normalized_keys = [normalize_key(k) for k in keys if normalize_key(k)]
        if normalized_keys and entries:
            for entry_key, entry_val in entries.items():
                normalized_entry = normalize_key(entry_key)
                if normalized_entry and normalized_entry in normalized_keys:
                    direct.entry = entry_val
                    direct.key = entry_key
                    direct.match_key = entry_key
                    direct.match_source = "direct"
                    return direct

    # Try parent keys
    parent_keys = parent_keys or []
    if parent_keys:
        parent = resolve_channel_entry_match(entries, parent_keys)
        if parent.entry is not None and parent.key is not None:
            direct.entry = parent.entry
            direct.key = parent.key
            direct.parent_entry = parent.entry
            direct.parent_key = parent.key
            direct.match_key = parent.key
            direct.match_source = "parent"
            return direct

        # Try normalized parent keys
        if normalize_key:
            normalized_parent_keys = [normalize_key(k) for k in parent_keys if normalize_key(k)]
            if normalized_parent_keys and entries:
                for entry_key, entry_val in entries.items():
                    normalized_entry = normalize_key(entry_key)
                    if normalized_entry and normalized_entry in normalized_parent_keys:
                        direct.entry = entry_val
                        direct.key = entry_key
                        direct.parent_entry = entry_val
                        direct.parent_key = entry_key
                        direct.match_key = entry_key
                        direct.match_source = "parent"
                        return direct

    # Wildcard fallback
    if direct.wildcard_entry is not None and direct.wildcard_key is not None:
        direct.entry = direct.wildcard_entry
        direct.key = direct.wildcard_key
        direct.match_key = direct.wildcard_key
        direct.match_source = "wildcard"
        return direct

    return direct


# ─── nested allowlist ───

def resolve_nested_allowlist_decision(
    outer_configured: bool,
    outer_matched: bool,
    inner_configured: bool,
    inner_matched: bool,
) -> bool:
    """Resolve nested allowlist decision (outer+inner layered filter)."""
    if not outer_configured:
        return True
    if not outer_matched:
        return False
    if not inner_configured:
        return True
    return inner_matched


def apply_channel_match_meta(result: dict[str, Any], match: ChannelEntryMatch) -> dict[str, Any]:
    """Apply match metadata (matchKey, matchSource) to a result dict."""
    if match.match_key and match.match_source:
        result["matchKey"] = match.match_key
        result["matchSource"] = match.match_source
    return result
