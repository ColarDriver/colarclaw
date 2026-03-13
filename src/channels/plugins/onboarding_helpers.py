"""Channels plugins.onboarding_helpers — ported from bk/src/channels/plugins/onboarding/helpers.ts.

Shared onboarding flow helpers: allow-from prompting, entry parsing,
account ID resolution, config patching, token prompt states.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from .setup_helpers import (
    DEFAULT_ACCOUNT_ID,
    normalize_account_id,
    move_single_account_channel_section_to_default_account,
)


# ─── allowFrom helpers ───

def add_wildcard_allow_from(allow_from: list[str | int] | None = None) -> list[str]:
    """Ensure allowFrom list contains wildcard '*'."""
    entries = [str(v).strip() for v in (allow_from or []) if str(v).strip()]
    if "*" not in entries:
        entries.append("*")
    return entries


def merge_allow_from_entries(
    current: list[str | int] | None,
    additions: list[str | int],
) -> list[str]:
    """Merge and deduplicate allowFrom entries."""
    combined = [str(v).strip() for v in list(current or []) + list(additions)]
    return list(dict.fromkeys(s for s in combined if s))


def split_onboarding_entries(raw: str) -> list[str]:
    """Split raw input into individual entries (newline, comma, or semicolon separated)."""
    return [s.strip() for s in re.split(r"[\n,;]+", raw) if s.strip()]


def normalize_allow_from_entries(
    entries: list[str | int],
    normalize_entry: Callable[[str], str | None] | None = None,
) -> list[str]:
    """Normalize allowFrom entries with optional per-entry normalization."""
    result = []
    for entry in entries:
        s = str(entry).strip()
        if not s:
            continue
        if s == "*":
            result.append("*")
            continue
        if normalize_entry:
            value = normalize_entry(s)
            if value and value.strip():
                result.append(value.strip())
        else:
            result.append(s)
    return list(dict.fromkeys(result))


# ─── entry parsing ───

def parse_onboarding_entries_with_parser(
    raw: str,
    parse_entry: Callable[[str], tuple[str | None, str | None]],
) -> tuple[list[str], str | None]:
    """Parse entries with a validator. Returns (entries, error)."""
    parts = split_onboarding_entries(str(raw or ""))
    entries: list[str] = []
    for part in parts:
        value, error = parse_entry(part)
        if error:
            return [], error
        if value:
            entries.append(value)
    return normalize_allow_from_entries(entries), None


def parse_onboarding_entries_allowing_wildcard(
    raw: str,
    parse_entry: Callable[[str], tuple[str | None, str | None]],
) -> tuple[list[str], str | None]:
    """Parse entries allowing '*' wildcard."""
    def _parse(entry: str) -> tuple[str | None, str | None]:
        if entry == "*":
            return "*", None
        return parse_entry(entry)
    return parse_onboarding_entries_with_parser(raw, _parse)


def parse_mention_or_prefixed_id(
    value: str,
    mention_pattern: re.Pattern[str],
    id_pattern: re.Pattern[str],
    prefix_pattern: re.Pattern[str] | None = None,
    normalize_id: Callable[[str], str] | None = None,
) -> str | None:
    """Parse a mention or prefixed ID."""
    trimmed = value.strip()
    if not trimmed:
        return None
    m = mention_pattern.search(trimmed)
    if m and m.group(1):
        return normalize_id(m.group(1)) if normalize_id else m.group(1)
    stripped = prefix_pattern.sub("", trimmed) if prefix_pattern else trimmed
    if not id_pattern.search(stripped):
        return None
    return normalize_id(stripped) if normalize_id else stripped


# ─── account resolution ───

def resolve_onboarding_account_id(
    account_id: str | None = None,
    default_account_id: str = DEFAULT_ACCOUNT_ID,
) -> str:
    if account_id and account_id.strip():
        return normalize_account_id(account_id)
    return default_account_id


# ─── config patching ───

def set_account_allow_from_for_channel(
    cfg: dict[str, Any],
    channel: str,
    account_id: str,
    allow_from: list[str],
) -> dict[str, Any]:
    """Set allowFrom for a specific channel account."""
    return _patch_config_for_scoped_account(
        cfg, channel, account_id,
        patch={"allowFrom": allow_from},
        ensure_enabled=False,
    )


def set_top_level_channel_allow_from(
    cfg: dict[str, Any],
    channel: str,
    allow_from: list[str],
    enabled: bool = False,
) -> dict[str, Any]:
    channels_cfg = cfg.get("channels", {})
    channel_cfg = dict(channels_cfg.get(channel, {}))
    if enabled:
        channel_cfg["enabled"] = True
    channel_cfg["allowFrom"] = allow_from
    return {**cfg, "channels": {**channels_cfg, channel: channel_cfg}}


def set_top_level_channel_dm_policy_with_allow_from(
    cfg: dict[str, Any],
    channel: str,
    dm_policy: str,
    get_allow_from: Callable[[dict[str, Any]], list[str | int] | None] | None = None,
) -> dict[str, Any]:
    channels_cfg = cfg.get("channels", {})
    channel_cfg = dict(channels_cfg.get(channel, {}))
    existing = get_allow_from(cfg) if get_allow_from else channel_cfg.get("allowFrom")
    allow_from = add_wildcard_allow_from(existing) if dm_policy == "open" else None
    channel_cfg["dmPolicy"] = dm_policy
    if allow_from:
        channel_cfg["allowFrom"] = allow_from
    return {**cfg, "channels": {**channels_cfg, channel: channel_cfg}}


def set_top_level_channel_group_policy(
    cfg: dict[str, Any],
    channel: str,
    group_policy: str,
    enabled: bool = False,
) -> dict[str, Any]:
    channels_cfg = cfg.get("channels", {})
    channel_cfg = dict(channels_cfg.get(channel, {}))
    if enabled:
        channel_cfg["enabled"] = True
    channel_cfg["groupPolicy"] = group_policy
    return {**cfg, "channels": {**channels_cfg, channel: channel_cfg}}


def set_channel_dm_policy_with_allow_from(
    cfg: dict[str, Any],
    channel: str,
    dm_policy: str,
) -> dict[str, Any]:
    channels_cfg = cfg.get("channels", {})
    channel_cfg = dict(channels_cfg.get(channel, {}))
    if dm_policy == "open":
        channel_cfg["allowFrom"] = add_wildcard_allow_from(channel_cfg.get("allowFrom"))
    channel_cfg["dmPolicy"] = dm_policy
    return {**cfg, "channels": {**channels_cfg, channel: channel_cfg}}


def set_onboarding_channel_enabled(
    cfg: dict[str, Any],
    channel: str,
    enabled: bool,
) -> dict[str, Any]:
    channels_cfg = cfg.get("channels", {})
    channel_cfg = dict(channels_cfg.get(channel, {}))
    channel_cfg["enabled"] = enabled
    return {**cfg, "channels": {**channels_cfg, channel: channel_cfg}}


def patch_channel_config_for_account(
    cfg: dict[str, Any],
    channel: str,
    account_id: str,
    patch: dict[str, Any],
) -> dict[str, Any]:
    return _patch_config_for_scoped_account(cfg, channel, account_id, patch, ensure_enabled=True)


def _patch_config_for_scoped_account(
    cfg: dict[str, Any],
    channel: str,
    account_id: str,
    patch: dict[str, Any],
    ensure_enabled: bool,
) -> dict[str, Any]:
    seeded = cfg
    if account_id != DEFAULT_ACCOUNT_ID:
        seeded = move_single_account_channel_section_to_default_account(cfg, channel)
    channels_cfg = seeded.get("channels", {})
    channel_cfg = dict(channels_cfg.get(channel, {}))

    if account_id == DEFAULT_ACCOUNT_ID:
        if ensure_enabled:
            channel_cfg["enabled"] = True
        channel_cfg.update(patch)
        return {**seeded, "channels": {**channels_cfg, channel: channel_cfg}}

    accounts = dict(channel_cfg.get("accounts", {}))
    existing = dict(accounts.get(account_id, {}))
    if ensure_enabled:
        channel_cfg["enabled"] = True
        existing.setdefault("enabled", True)
    existing.update(patch)
    accounts[account_id] = existing
    channel_cfg["accounts"] = accounts
    return {**seeded, "channels": {**channels_cfg, channel: channel_cfg}}
