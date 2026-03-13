"""Channels plugin catalog — ported from bk/src/channels/plugins/catalog.ts,
index.ts, status.ts, helpers.ts.

Channel plugin catalog (registration, lookup), status assessment,
and media limit resolution.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from .types import ChannelPlugin, ChannelAccountSnapshot, ChannelStatusIssue

logger = logging.getLogger("channels.plugins.catalog")


# ─── catalog.ts ───

@dataclass
class ChannelRegistryEntry:
    plugin: ChannelPlugin
    dock: Any = None


class ChannelPluginRegistry:
    """Registry for channel plugins."""

    def __init__(self) -> None:
        self.channels: list[ChannelRegistryEntry] = []
        self._by_id: dict[str, ChannelRegistryEntry] = {}

    def register(self, plugin: ChannelPlugin, dock: Any = None) -> None:
        plugin_id = plugin.id.strip()
        if not plugin_id:
            raise ValueError("Channel plugin id is required")
        if plugin_id in self._by_id:
            logger.warning(f"Channel plugin '{plugin_id}' already registered, replacing")
        entry = ChannelRegistryEntry(plugin=plugin, dock=dock)
        self.channels = [e for e in self.channels if e.plugin.id != plugin_id]
        self.channels.append(entry)
        self._by_id[plugin_id] = entry

    def get(self, channel_id: str) -> ChannelRegistryEntry | None:
        return self._by_id.get(channel_id.strip())

    def find_by_alias(self, alias: str) -> ChannelRegistryEntry | None:
        key = alias.strip().lower()
        for entry in self.channels:
            if entry.plugin.id.lower() == key:
                return entry
            for a in entry.plugin.meta.aliases:
                if a.lower() == key:
                    return entry
        return None

    def list_ids(self) -> list[str]:
        return [e.plugin.id for e in self.channels]


# Global registry (singleton)
_active_registry: ChannelPluginRegistry | None = None


def get_active_plugin_registry() -> ChannelPluginRegistry | None:
    return _active_registry


def require_active_plugin_registry() -> ChannelPluginRegistry:
    if not _active_registry:
        raise RuntimeError("Channel plugin registry not initialized")
    return _active_registry


def set_active_plugin_registry(registry: ChannelPluginRegistry) -> None:
    global _active_registry
    _active_registry = registry


# ─── status.ts ───

@dataclass
class ChannelStatusResult:
    channel: str = ""
    account_id: str = ""
    configured: bool = False
    connected: bool = False
    running: bool = False
    issues: list[ChannelStatusIssue] = field(default_factory=list)
    snapshot: ChannelAccountSnapshot | None = None


def assess_channel_status(
    channel_id: str,
    snapshot: ChannelAccountSnapshot | None = None,
) -> ChannelStatusResult:
    """Assess channel status from snapshot."""
    if not snapshot:
        return ChannelStatusResult(
            channel=channel_id, configured=False,
        )
    return ChannelStatusResult(
        channel=channel_id,
        account_id=snapshot.account_id,
        configured=snapshot.configured or False,
        connected=snapshot.connected or False,
        running=snapshot.running or False,
        snapshot=snapshot,
    )


# ─── media-limits.ts ───

CHANNEL_MEDIA_MAX_BYTES: dict[str, int] = {
    "telegram": 50 * 1024 * 1024,  # 50 MiB
    "whatsapp": 16 * 1024 * 1024,  # 16 MiB
    "discord": 25 * 1024 * 1024,   # 25 MiB (Nitro allows up to 100 MiB)
    "slack": 1024 * 1024 * 1024,   # 1 GiB
    "signal": 100 * 1024 * 1024,   # 100 MiB
    "imessage": 100 * 1024 * 1024, # 100 MiB
    "line": 200 * 1024 * 1024,     # 200 MiB
}


def resolve_channel_media_max_bytes(channel_id: str) -> int:
    """Resolve the max media size in bytes for a channel."""
    return CHANNEL_MEDIA_MAX_BYTES.get(channel_id.lower(), 25 * 1024 * 1024)


# ─── helpers.ts ───

def resolve_optional_config_string(value: Any) -> str | None:
    """Resolve an optional config string, returning None if empty."""
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed or None
    return None


def map_allow_from_entries(raw: list[Any] | None) -> list[str]:
    """Map raw allowFrom config values to normalized string list."""
    if not raw:
        return []
    return [str(v).strip() for v in raw if str(v).strip()]


# ─── config-helpers.ts ───

def format_normalized_allow_from_entries(
    allow_from: list[str | int],
    normalize_entry: Callable[[str], str] | None = None,
) -> list[str]:
    """Format allowFrom entries with optional normalization."""
    result = []
    for entry in allow_from:
        s = str(entry).strip()
        if not s:
            continue
        if normalize_entry:
            s = normalize_entry(s)
        if s:
            result.append(s)
    return result


def format_allow_from_lowercase(
    allow_from: list[str | int],
    strip_prefix_re: Any = None,
) -> list[str]:
    """Format allowFrom entries to lowercase with optional prefix stripping."""
    import re as _re
    result = []
    for entry in allow_from:
        s = str(entry).strip()
        if strip_prefix_re:
            s = strip_prefix_re.sub("", s)
        s = s.strip().lower()
        if s:
            result.append(s)
    return result
