"""Channels plugins.status_issues — ported from bk/src/channels/plugins/status-issues/*.ts.

Channel status issue detection (config warnings, permission checks,
auth diagnostics) for each channel.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .types import ChannelStatusIssue


# ─── shared.ts ───

def create_config_issue(
    channel: str,
    account_id: str,
    message: str,
    fix: str = "",
) -> ChannelStatusIssue:
    return ChannelStatusIssue(
        channel=channel, account_id=account_id,
        kind="config", message=message, fix=fix,
    )


def create_auth_issue(
    channel: str,
    account_id: str,
    message: str,
    fix: str = "",
) -> ChannelStatusIssue:
    return ChannelStatusIssue(
        channel=channel, account_id=account_id,
        kind="auth", message=message, fix=fix,
    )


def create_runtime_issue(
    channel: str,
    account_id: str,
    message: str,
    fix: str = "",
) -> ChannelStatusIssue:
    return ChannelStatusIssue(
        channel=channel, account_id=account_id,
        kind="runtime", message=message, fix=fix,
    )


def create_permissions_issue(
    channel: str,
    account_id: str,
    message: str,
    fix: str = "",
) -> ChannelStatusIssue:
    return ChannelStatusIssue(
        channel=channel, account_id=account_id,
        kind="permissions", message=message, fix=fix,
    )


# ─── channel-specific issue checks ───

def check_token_configured(
    channel: str,
    account_id: str,
    token: str | None,
    token_label: str = "token",
    config_path: str = "",
) -> ChannelStatusIssue | None:
    """Check if a required token is configured."""
    if token and token.strip():
        return None
    fix = f"Set {config_path}" if config_path else f"Configure the {token_label}"
    return create_config_issue(
        channel, account_id,
        f"{token_label} is not configured",
        fix=fix,
    )


def check_allow_from_configured(
    channel: str,
    account_id: str,
    allow_from: list[str] | None,
    dm_policy: str = "",
) -> ChannelStatusIssue | None:
    """Check if allowFrom is configured when using allowlist policy."""
    if dm_policy != "allowlist":
        return None
    if allow_from and len(allow_from) > 0:
        return None
    return create_config_issue(
        channel, account_id,
        "allowFrom is empty but dm policy is 'allowlist'",
        fix=f"Add entries to channels.{channel}.allowFrom",
    )
