"""Channels model_overrides — ported from bk/src/channels/model-overrides.ts.

Per-channel/group model override resolution based on channel config.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .config import (
    build_channel_key_candidates,
    normalize_channel_slug,
    resolve_channel_entry_match_with_fallback,
)

THREAD_SUFFIX_REGEX = re.compile(r":(?:thread|topic):[^:]+$", re.IGNORECASE)


@dataclass
class ChannelModelOverride:
    channel: str
    model: str
    match_key: str | None = None
    match_source: str | None = None


def _normalize_message_channel(channel: str | None) -> str | None:
    if not channel:
        return None
    return channel.strip().lower()


def _resolve_provider_entry(
    model_by_channel: dict[str, dict[str, str]] | None,
    channel: str,
) -> dict[str, str] | None:
    if not model_by_channel:
        return None
    normalized = _normalize_message_channel(channel) or channel.strip().lower()
    if normalized in model_by_channel:
        return model_by_channel[normalized]
    for key in model_by_channel:
        key_norm = _normalize_message_channel(key) or key.strip().lower()
        if key_norm == normalized:
            return model_by_channel[key]
    return None


def _resolve_parent_group_id(group_id: str | None) -> str | None:
    raw = (group_id or "").strip()
    if not raw or not THREAD_SUFFIX_REGEX.search(raw):
        return None
    parent = THREAD_SUFFIX_REGEX.sub("", raw).strip()
    return parent if parent and parent != raw else None


def resolve_channel_model_override(
    cfg: dict[str, Any],
    channel: str | None = None,
    group_id: str | None = None,
    group_channel: str | None = None,
    group_subject: str | None = None,
    parent_session_key: str | None = None,
) -> ChannelModelOverride | None:
    """Resolve a per-channel/group model override from config."""
    ch = (channel or "").strip()
    if not ch:
        return None

    channels_cfg = cfg.get("channels", {})
    model_by_channel = channels_cfg.get("modelByChannel")
    if not model_by_channel:
        return None

    provider_entries = _resolve_provider_entry(model_by_channel, ch)
    if not provider_entries:
        return None

    # Build candidate keys
    gid = (group_id or "").strip()
    parent_gid = _resolve_parent_group_id(gid) if gid else None
    gc = (group_channel or "").strip()
    gs = (group_subject or "").strip()

    raw_keys = [
        gid, parent_gid,
        gc, gc.lstrip("#") if gc else None,
        normalize_channel_slug(gc.lstrip("#")) if gc else None,
        gs, gs.lstrip("#") if gs else None,
        normalize_channel_slug(gs.lstrip("#")) if gs else None,
    ]
    candidates = build_channel_key_candidates(*raw_keys)
    if not candidates:
        return None

    match = resolve_channel_entry_match_with_fallback(
        entries=provider_entries,
        keys=candidates,
        wildcard_key="*",
        normalize_key=lambda v: v.strip().lower(),
    )
    raw = match.entry if match.entry is not None else (match.wildcard_entry if match.wildcard_entry is not None else None)
    if not isinstance(raw, str):
        return None
    model = raw.strip()
    if not model:
        return None

    return ChannelModelOverride(
        channel=_normalize_message_channel(ch) or ch.strip().lower(),
        model=model,
        match_key=match.match_key,
        match_source=match.match_source,
    )
