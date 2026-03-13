"""Channels plugins.setup_helpers — ported from bk/src/channels/plugins/setup-helpers.ts.

Account name migration, single→multi account promotion, config patching.
"""
from __future__ import annotations

import copy
from typing import Any

DEFAULT_ACCOUNT_ID = "default"


def normalize_account_id(value: str | None) -> str:
    return (value or "default").strip().lower()


def _channel_has_accounts(cfg: dict[str, Any], channel_key: str) -> bool:
    channels = cfg.get("channels", {})
    base = channels.get(channel_key, {})
    accounts = base.get("accounts", {})
    return bool(accounts and len(accounts) > 0)


# ─── keys that move from channel root to accounts.default ───

COMMON_SINGLE_ACCOUNT_KEYS_TO_MOVE = {
    "name", "token", "tokenFile", "botToken", "appToken", "account",
    "signalNumber", "authDir", "cliPath", "dbPath",
    "httpUrl", "httpHost", "httpPort", "webhookPath", "webhookUrl", "webhookSecret",
    "service", "region", "homeserver", "userId", "accessToken", "password",
    "deviceName", "url", "code",
    "dmPolicy", "allowFrom", "groupPolicy", "groupAllowFrom", "defaultTo",
}

CHANNEL_SPECIFIC_KEYS: dict[str, set[str]] = {
    "telegram": {"streaming"},
}


def should_move_single_account_channel_key(channel_key: str, key: str) -> bool:
    if key in COMMON_SINGLE_ACCOUNT_KEYS_TO_MOVE:
        return True
    return key in CHANNEL_SPECIFIC_KEYS.get(channel_key, set())


def move_single_account_channel_section_to_default_account(
    cfg: dict[str, Any],
    channel_key: str,
) -> dict[str, Any]:
    """Promote single-account channel config to multi-account."""
    channels = cfg.get("channels", {})
    base = channels.get(channel_key)
    if not base or not isinstance(base, dict):
        return cfg
    accounts = base.get("accounts", {})
    if accounts and len(accounts) > 0:
        return cfg

    keys_to_move = [
        k for k, v in base.items()
        if k not in ("accounts", "enabled")
        and v is not None
        and should_move_single_account_channel_key(channel_key, k)
    ]
    default_account: dict[str, Any] = {}
    for k in keys_to_move:
        default_account[k] = copy.deepcopy(base[k])

    next_channel = {k: v for k, v in base.items() if k not in keys_to_move}
    next_channel["accounts"] = {
        **accounts,
        DEFAULT_ACCOUNT_ID: default_account,
    }

    return {
        **cfg,
        "channels": {
            **channels,
            channel_key: next_channel,
        },
    }


def apply_account_name_to_channel_section(
    cfg: dict[str, Any],
    channel_key: str,
    account_id: str,
    name: str | None = None,
    always_use_accounts: bool = False,
) -> dict[str, Any]:
    """Apply an account name to the channel config section."""
    trimmed = (name or "").strip()
    if not trimmed:
        return cfg
    acct_id = normalize_account_id(account_id)
    channels = cfg.get("channels", {})
    base = channels.get(channel_key, {})

    use_accounts = always_use_accounts or acct_id != DEFAULT_ACCOUNT_ID or _channel_has_accounts(cfg, channel_key)

    if not use_accounts and acct_id == DEFAULT_ACCOUNT_ID:
        return {
            **cfg,
            "channels": {
                **channels,
                channel_key: {**base, "name": trimmed},
            },
        }

    accounts = base.get("accounts", {})
    existing = accounts.get(acct_id, {})
    base_copy = {k: v for k, v in base.items() if k != "name"} if acct_id == DEFAULT_ACCOUNT_ID else dict(base)

    return {
        **cfg,
        "channels": {
            **channels,
            channel_key: {
                **base_copy,
                "accounts": {
                    **accounts,
                    acct_id: {**existing, "name": trimmed},
                },
            },
        },
    }


def apply_setup_account_config_patch(
    cfg: dict[str, Any],
    channel_key: str,
    account_id: str,
    patch: dict[str, Any],
) -> dict[str, Any]:
    """Apply a config patch to a channel account."""
    acct_id = normalize_account_id(account_id)
    channels = cfg.get("channels", {})
    base = channels.get(channel_key, {})

    if acct_id == DEFAULT_ACCOUNT_ID:
        return {
            **cfg,
            "channels": {
                **channels,
                channel_key: {**base, "enabled": True, **patch},
            },
        }

    accounts = base.get("accounts", {})
    return {
        **cfg,
        "channels": {
            **channels,
            channel_key: {
                **base,
                "enabled": True,
                "accounts": {
                    **accounts,
                    acct_id: {
                        **accounts.get(acct_id, {}),
                        "enabled": True,
                        **patch,
                    },
                },
            },
        },
    }


def migrate_base_name_to_default_account(
    cfg: dict[str, Any],
    channel_key: str,
    always_use_accounts: bool = False,
) -> dict[str, Any]:
    """Migrate root-level name to accounts.default."""
    if always_use_accounts:
        return cfg
    channels = cfg.get("channels", {})
    base = channels.get(channel_key, {})
    base_name = (base.get("name") or "").strip()
    if not base_name:
        return cfg

    accounts = dict(base.get("accounts", {}))
    default_acct = dict(accounts.get(DEFAULT_ACCOUNT_ID, {}))
    if not default_acct.get("name"):
        default_acct["name"] = base_name
    accounts[DEFAULT_ACCOUNT_ID] = default_acct

    rest = {k: v for k, v in base.items() if k != "name"}
    return {
        **cfg,
        "channels": {
            **channels,
            channel_key: {**rest, "accounts": accounts},
        },
    }
