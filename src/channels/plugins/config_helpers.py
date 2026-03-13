"""Channels plugins.config_helpers — ported from bk/src/channels/plugins/config-helpers.ts,
config-schema.ts, config-writes.ts, pairing.ts, pairing-message.ts,
account-helpers.ts, allowlist-match.ts, channel-config.ts.

Config helpers, schema validation, pairing, and account utilities.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from .setup_helpers import DEFAULT_ACCOUNT_ID, normalize_account_id


# ─── config-helpers.ts ───

def resolve_channel_config_string(
    cfg: dict[str, Any],
    channel: str,
    key: str,
    account_id: str = "",
) -> str | None:
    """Resolve a string config value for a channel, with account fallback."""
    channels_cfg = cfg.get("channels", {})
    channel_cfg = channels_cfg.get(channel, {})
    if account_id:
        acct = channel_cfg.get("accounts", {}).get(account_id, {})
        value = acct.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    value = channel_cfg.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def resolve_channel_config_list(
    cfg: dict[str, Any],
    channel: str,
    key: str,
    account_id: str = "",
) -> list[str]:
    """Resolve a list config value."""
    channels_cfg = cfg.get("channels", {})
    channel_cfg = channels_cfg.get(channel, {})
    if account_id:
        acct = channel_cfg.get("accounts", {}).get(account_id, {})
        value = acct.get(key)
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
    value = channel_cfg.get(key)
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def resolve_channel_config_bool(
    cfg: dict[str, Any],
    channel: str,
    key: str,
    default: bool = False,
    account_id: str = "",
) -> bool:
    """Resolve a boolean config value."""
    channels_cfg = cfg.get("channels", {})
    channel_cfg = channels_cfg.get(channel, {})
    if account_id:
        acct = channel_cfg.get("accounts", {}).get(account_id, {})
        value = acct.get(key)
        if isinstance(value, bool):
            return value
    value = channel_cfg.get(key)
    if isinstance(value, bool):
        return value
    return default


# ─── config-schema.ts ───

def validate_channel_config_schema(
    cfg: dict[str, Any],
    channel: str,
) -> list[str]:
    """Validate basic channel config schema, returning error list."""
    errors: list[str] = []
    channels_cfg = cfg.get("channels", {})
    channel_cfg = channels_cfg.get(channel, {})

    if not isinstance(channel_cfg, dict):
        errors.append(f"channels.{channel} must be an object")
        return errors

    # Validate known keys
    allow_from = channel_cfg.get("allowFrom")
    if allow_from is not None and not isinstance(allow_from, list):
        errors.append(f"channels.{channel}.allowFrom must be an array")

    dm_policy = channel_cfg.get("dmPolicy")
    if dm_policy is not None and dm_policy not in ("open", "allowlist", "pairing", "paired"):
        errors.append(f"channels.{channel}.dmPolicy must be one of: open, allowlist, pairing, paired")

    return errors


# ─── config-writes.ts ───

def write_channel_config_value(
    cfg: dict[str, Any],
    channel: str,
    key: str,
    value: Any,
    account_id: str = "",
) -> dict[str, Any]:
    """Write a config value to a channel section."""
    channels_cfg = dict(cfg.get("channels", {}))
    channel_cfg = dict(channels_cfg.get(channel, {}))

    if account_id and account_id != DEFAULT_ACCOUNT_ID:
        accounts = dict(channel_cfg.get("accounts", {}))
        acct = dict(accounts.get(account_id, {}))
        acct[key] = value
        accounts[account_id] = acct
        channel_cfg["accounts"] = accounts
    else:
        channel_cfg[key] = value

    channels_cfg[channel] = channel_cfg
    return {**cfg, "channels": channels_cfg}


# ─── pairing.ts ───

def resolve_pairing_config(
    cfg: dict[str, Any],
    channel: str,
    account_id: str = "",
) -> dict[str, Any]:
    """Resolve pairing config for a channel."""
    channels_cfg = cfg.get("channels", {})
    channel_cfg = channels_cfg.get(channel, {})
    pairing = channel_cfg.get("pairing", {})
    if account_id:
        acct = channel_cfg.get("accounts", {}).get(account_id, {})
        acct_pairing = acct.get("pairing", {})
        pairing = {**pairing, **acct_pairing}
    return pairing


def is_pairing_enabled(cfg: dict[str, Any], channel: str, account_id: str = "") -> bool:
    dm_policy = resolve_channel_config_string(cfg, channel, "dmPolicy", account_id) or ""
    return dm_policy in ("pairing", "paired")


# ─── pairing-message.ts ───

PAIRING_MESSAGE_TEMPLATE = "Hi! I'd like to chat. My pairing code is: {code}"


def format_pairing_message(code: str | None = None) -> str:
    if code:
        return PAIRING_MESSAGE_TEMPLATE.format(code=code)
    return "Hi! I'd like to chat."


# ─── account-helpers.ts ───

def list_channel_account_ids(
    cfg: dict[str, Any],
    channel: str,
) -> list[str]:
    """List all account IDs for a channel."""
    channels_cfg = cfg.get("channels", {})
    channel_cfg = channels_cfg.get(channel, {})
    accounts = channel_cfg.get("accounts", {})
    if accounts and isinstance(accounts, dict):
        return list(accounts.keys())
    # Check if top-level channel config has any account markers
    if channel_cfg.get("token") or channel_cfg.get("botToken") or channel_cfg.get("enabled"):
        return [DEFAULT_ACCOUNT_ID]
    return []


def resolve_default_account_id(
    cfg: dict[str, Any],
    channel: str,
) -> str:
    """Resolve the default account ID for a channel."""
    ids = list_channel_account_ids(cfg, channel)
    return ids[0] if ids else DEFAULT_ACCOUNT_ID
