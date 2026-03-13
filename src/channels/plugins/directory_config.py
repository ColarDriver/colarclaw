"""Channels plugins.directory_config — ported from bk/src/channels/plugins/directory-config.ts,
directory-config-helpers.ts.

Channel directory configuration: contact/group lookup, caching, and resolution.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .types import ChannelDirectoryEntry


# ─── directory-config-helpers.ts ───

@dataclass
class DirectoryLookupResult:
    entries: list[ChannelDirectoryEntry] = field(default_factory=list)
    error: str | None = None
    cached: bool = False


@dataclass
class DirectoryConfig:
    enabled: bool = True
    cache_ttl_ms: int = 300_000  # 5 minutes
    max_entries: int = 1000


def resolve_directory_config(
    cfg: dict[str, Any],
    channel: str,
    account_id: str = "",
) -> DirectoryConfig:
    """Resolve directory config for a channel."""
    channels_cfg = cfg.get("channels", {})
    channel_cfg = channels_cfg.get(channel, {})
    dir_cfg = channel_cfg.get("directory", {})

    return DirectoryConfig(
        enabled=dir_cfg.get("enabled", True),
        cache_ttl_ms=dir_cfg.get("cacheTtlMs", 300_000),
        max_entries=dir_cfg.get("maxEntries", 1000),
    )


# ─── directory-config.ts ───


class DirectoryCache:
    """In-memory directory entry cache with TTL."""

    def __init__(self, ttl_ms: int = 300_000):
        self._ttl_ms = ttl_ms
        self._cache: dict[str, tuple[list[ChannelDirectoryEntry], float]] = {}

    def get(self, key: str) -> list[ChannelDirectoryEntry] | None:
        entry = self._cache.get(key)
        if not entry:
            return None
        entries, ts = entry
        if (time.time() * 1000 - ts) > self._ttl_ms:
            del self._cache[key]
            return None
        return entries

    def set(self, key: str, entries: list[ChannelDirectoryEntry]) -> None:
        self._cache[key] = (entries, time.time() * 1000)

    def invalidate(self, key: str) -> None:
        self._cache.pop(key, None)

    def clear(self) -> None:
        self._cache.clear()


def normalize_directory_query(query: str) -> str:
    """Normalize a directory search query."""
    return query.strip().lower()


def filter_directory_entries(
    entries: list[ChannelDirectoryEntry],
    query: str,
    max_results: int = 25,
) -> list[ChannelDirectoryEntry]:
    """Filter directory entries by query string."""
    if not query:
        return entries[:max_results]
    q = normalize_directory_query(query)
    matched = []
    for entry in entries:
        if (
            q in entry.name.lower()
            or q in entry.handle.lower()
            or q in entry.id.lower()
        ):
            matched.append(entry)
            if len(matched) >= max_results:
                break
    return matched


def rank_directory_entries(
    entries: list[ChannelDirectoryEntry],
    query: str,
) -> list[ChannelDirectoryEntry]:
    """Rank directory entries by relevance to query."""
    q = normalize_directory_query(query)
    if not q:
        return entries

    def score(entry: ChannelDirectoryEntry) -> int:
        s = 0
        name_lower = entry.name.lower()
        handle_lower = entry.handle.lower()
        if name_lower == q or handle_lower == q:
            s += 100
        elif name_lower.startswith(q) or handle_lower.startswith(q):
            s += 50
        elif q in name_lower or q in handle_lower:
            s += 10
        s += entry.rank
        return s

    return sorted(entries, key=score, reverse=True)
