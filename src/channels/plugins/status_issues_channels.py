"""Channels plugins.status_issues_channels — ported from bk/src/channels/plugins/status-issues/{telegram,discord,whatsapp,bluebubbles}.ts.

Per-channel status issue detection.
"""
from __future__ import annotations

from typing import Any

from .status_issues import (
    ChannelStatusIssue,
    create_config_issue,
    create_auth_issue,
    create_runtime_issue,
    create_permissions_issue,
    check_token_configured,
    check_allow_from_configured,
)


# ─── Telegram ───

def check_telegram_status_issues(
    cfg: dict[str, Any],
    account_id: str = "",
    snapshot: dict[str, Any] | None = None,
) -> list[ChannelStatusIssue]:
    issues: list[ChannelStatusIssue] = []
    tg_cfg = cfg.get("channels", {}).get("telegram", {})
    acct = tg_cfg.get("accounts", {}).get(account_id, tg_cfg) if account_id else tg_cfg

    # Token check
    token_issue = check_token_configured(
        "telegram", account_id,
        acct.get("botToken") or acct.get("token") or acct.get("tokenFile"),
        "bot token",
        "channels.telegram.botToken",
    )
    if token_issue:
        issues.append(token_issue)

    # AllowFrom check
    af_issue = check_allow_from_configured(
        "telegram", account_id,
        acct.get("allowFrom"),
        acct.get("dmPolicy", ""),
    )
    if af_issue:
        issues.append(af_issue)

    # Probe check
    if snapshot and snapshot.get("probe"):
        probe = snapshot["probe"]
        if isinstance(probe, dict) and not probe.get("ok"):
            issues.append(create_runtime_issue(
                "telegram", account_id,
                f"Probe failed: {probe.get('error', 'unknown')}",
            ))

    return issues


# ─── Discord ───

def check_discord_status_issues(
    cfg: dict[str, Any],
    account_id: str = "",
    snapshot: dict[str, Any] | None = None,
) -> list[ChannelStatusIssue]:
    issues: list[ChannelStatusIssue] = []
    dc_cfg = cfg.get("channels", {}).get("discord", {})
    acct = dc_cfg.get("accounts", {}).get(account_id, dc_cfg) if account_id else dc_cfg

    # Token check
    token_issue = check_token_configured(
        "discord", account_id,
        acct.get("token") or acct.get("botToken"),
        "bot token",
        "channels.discord.token",
    )
    if token_issue:
        issues.append(token_issue)

    # Intents check
    if snapshot and snapshot.get("probe"):
        probe = snapshot["probe"]
        if isinstance(probe, dict):
            if probe.get("missingIntents"):
                issues.append(create_permissions_issue(
                    "discord", account_id,
                    f"Missing intents: {', '.join(probe['missingIntents'])}",
                    fix="Enable required intents in Discord Developer Portal",
                ))

    # Application check
    if snapshot and snapshot.get("application"):
        app = snapshot["application"]
        if isinstance(app, dict) and not app.get("bot"):
            issues.append(create_config_issue(
                "discord", account_id,
                "Discord application has no bot user",
                fix="Add a bot to your Discord application in the Developer Portal",
            ))

    return issues


# ─── WhatsApp ───

def check_whatsapp_status_issues(
    cfg: dict[str, Any],
    account_id: str = "",
    snapshot: dict[str, Any] | None = None,
) -> list[ChannelStatusIssue]:
    issues: list[ChannelStatusIssue] = []

    if snapshot:
        if not snapshot.get("connected"):
            issues.append(create_runtime_issue(
                "whatsapp", account_id,
                "WhatsApp is not connected",
                fix="Run 'openclaw whatsapp link' to scan QR code",
            ))
        if snapshot.get("lastDisconnect"):
            dc = snapshot["lastDisconnect"]
            if isinstance(dc, dict) and dc.get("loggedOut"):
                issues.append(create_auth_issue(
                    "whatsapp", account_id,
                    "WhatsApp session logged out",
                    fix="Re-link with 'openclaw whatsapp link'",
                ))

    return issues


# ─── BlueBubbles ───

def check_bluebubbles_status_issues(
    cfg: dict[str, Any],
    account_id: str = "",
    snapshot: dict[str, Any] | None = None,
) -> list[ChannelStatusIssue]:
    issues: list[ChannelStatusIssue] = []
    bb_cfg = cfg.get("channels", {}).get("bluebubbles", {})
    acct = bb_cfg.get("accounts", {}).get(account_id, bb_cfg) if account_id else bb_cfg

    # URL check
    url = acct.get("url") or acct.get("httpUrl")
    if not url or not str(url).strip():
        issues.append(create_config_issue(
            "bluebubbles", account_id,
            "BlueBubbles server URL not configured",
            fix="Set channels.bluebubbles.url",
        ))

    # Password check
    password = acct.get("password")
    if not password or not str(password).strip():
        issues.append(create_config_issue(
            "bluebubbles", account_id,
            "BlueBubbles password not configured",
            fix="Set channels.bluebubbles.password",
        ))

    return issues


# ─── registry ───

STATUS_ISSUE_CHECKERS: dict[str, Any] = {
    "telegram": check_telegram_status_issues,
    "discord": check_discord_status_issues,
    "whatsapp": check_whatsapp_status_issues,
    "bluebubbles": check_bluebubbles_status_issues,
}


def check_channel_status_issues(
    channel: str,
    cfg: dict[str, Any],
    account_id: str = "",
    snapshot: dict[str, Any] | None = None,
) -> list[ChannelStatusIssue]:
    checker = STATUS_ISSUE_CHECKERS.get(channel)
    if not checker:
        return []
    return checker(cfg, account_id, snapshot)
