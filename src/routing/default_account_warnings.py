"""Default account warnings — ported from bk/src/routing/default-account-warnings.ts.

Config path formatting helpers for account warnings.
"""
from __future__ import annotations


def format_channel_default_account_path(channel_key: str) -> str:
    return f"channels.{channel_key}.defaultAccount"


def format_channel_accounts_default_path(channel_key: str) -> str:
    return f"channels.{channel_key}.accounts.default"


def format_set_explicit_default_instruction(channel_key: str) -> str:
    return (
        f"Set {format_channel_default_account_path(channel_key)} "
        f"or add {format_channel_accounts_default_path(channel_key)}"
    )


def format_set_explicit_default_to_configured_instruction(channel_key: str) -> str:
    return (
        f"Set {format_channel_default_account_path(channel_key)} to one of these accounts, "
        f"or add {format_channel_accounts_default_path(channel_key)}"
    )
