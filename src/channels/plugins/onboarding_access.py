"""Channels plugins.onboarding_access — ported from bk/src/channels/plugins/onboarding/channel-access.ts,
channel-access-configure.ts.

Channel access configuration for onboarding: DM policy, group policy,
allowFrom management.
"""
from __future__ import annotations

from typing import Any

from .onboarding_helpers import (
    add_wildcard_allow_from,
    set_channel_dm_policy_with_allow_from,
    set_top_level_channel_dm_policy_with_allow_from,
    set_top_level_channel_group_policy,
)


# ─── channel-access.ts ───

DM_POLICY_OPTIONS = [
    {"value": "open", "label": "Open — anyone can DM", "hint": "adds wildcard * to allowFrom"},
    {"value": "pairing", "label": "Pairing — require a pairing code first"},
    {"value": "allowlist", "label": "Allowlist — only listed senders"},
]

GROUP_POLICY_OPTIONS = [
    {"value": "open", "label": "Open — join any group"},
    {"value": "allowlist", "label": "Allowlist — only listed groups"},
    {"value": "none", "label": "None — ignore all groups"},
]


def resolve_current_dm_policy(
    cfg: dict[str, Any],
    channel: str,
    account_id: str = "",
) -> str:
    """Resolve current DM policy value."""
    channels_cfg = cfg.get("channels", {})
    channel_cfg = channels_cfg.get(channel, {})
    if account_id:
        acct = channel_cfg.get("accounts", {}).get(account_id, {})
        if "dmPolicy" in acct:
            return acct["dmPolicy"]
    return channel_cfg.get("dmPolicy", "pairing")


def resolve_current_group_policy(
    cfg: dict[str, Any],
    channel: str,
    account_id: str = "",
) -> str:
    """Resolve current group policy value."""
    channels_cfg = cfg.get("channels", {})
    channel_cfg = channels_cfg.get(channel, {})
    if account_id:
        acct = channel_cfg.get("accounts", {}).get(account_id, {})
        if "groupPolicy" in acct:
            return acct["groupPolicy"]
    return channel_cfg.get("groupPolicy", "open")


# ─── channel-access-configure.ts ───

def apply_dm_policy_change(
    cfg: dict[str, Any],
    channel: str,
    new_policy: str,
    account_id: str = "",
) -> dict[str, Any]:
    """Apply a DM policy change to config."""
    if channel in ("imessage", "signal", "telegram"):
        return set_channel_dm_policy_with_allow_from(cfg, channel, new_policy)
    return set_top_level_channel_dm_policy_with_allow_from(cfg, channel, new_policy)


def apply_group_policy_change(
    cfg: dict[str, Any],
    channel: str,
    new_policy: str,
    account_id: str = "",
) -> dict[str, Any]:
    """Apply a group policy change to config."""
    return set_top_level_channel_group_policy(cfg, channel, new_policy)
