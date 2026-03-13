"""Channels plugins.normalize — ported from bk/src/channels/plugins/normalize/*.ts.

Channel-specific target normalization for Signal, Discord, Telegram,
iMessage, Slack, WhatsApp.
"""
from __future__ import annotations

import re


# ─── shared ───

def strip_prefix(raw: str, prefix: str) -> str:
    if raw.lower().startswith(prefix.lower()):
        return raw[len(prefix):].strip()
    return raw


# ─── signal ───

E164_RE = re.compile(r"^\+?[1-9]\d{6,14}$")


def normalize_signal_messaging_target(raw: str | None) -> str | None:
    """Normalize a Signal messaging target (phone number or group ID)."""
    if not raw:
        return None
    trimmed = raw.strip()
    if not trimmed:
        return None
    # Strip signal: prefix
    clean = strip_prefix(trimmed, "signal:")
    # If it looks like E.164 phone number
    digits = re.sub(r"[\s\-\(\)]+", "", clean)
    if E164_RE.match(digits):
        if not digits.startswith("+"):
            digits = f"+{digits}"
        return digits
    # Group ID or other identifier
    return clean.lower()


# ─── discord ───

DISCORD_USER_MENTION_RE = re.compile(r"<@!?(\d+)>")
DISCORD_CHANNEL_RE = re.compile(r"<#(\d+)>")


def normalize_discord_target(raw: str | None) -> str | None:
    if not raw:
        return None
    trimmed = raw.strip()
    if not trimmed:
        return None
    clean = strip_prefix(trimmed, "discord:")
    clean = strip_prefix(clean, "user:")
    clean = strip_prefix(clean, "pk:")
    # Strip mention markers
    m = DISCORD_USER_MENTION_RE.match(clean)
    if m:
        return m.group(1)
    m = DISCORD_CHANNEL_RE.match(clean)
    if m:
        return m.group(1)
    return clean.strip().lower()


# ─── telegram ───

def normalize_telegram_target(raw: str | None) -> str | None:
    if not raw:
        return None
    trimmed = raw.strip()
    if not trimmed:
        return None
    clean = strip_prefix(trimmed, "telegram:")
    clean = strip_prefix(clean, "tg:")
    return clean.strip().lower()


# ─── imessage ───

def normalize_imessage_target(raw: str | None) -> str | None:
    if not raw:
        return None
    trimmed = raw.strip()
    if not trimmed:
        return None
    clean = strip_prefix(trimmed, "imessage:")
    clean = strip_prefix(clean, "imsg:")
    return clean.strip().lower()


# ─── slack ───

def normalize_slack_target(raw: str | None) -> str | None:
    if not raw:
        return None
    trimmed = raw.strip()
    if not trimmed:
        return None
    clean = strip_prefix(trimmed, "slack:")
    # Strip <@USER_ID> syntax
    clean = re.sub(r"^<@([^>]+)>$", r"\1", clean)
    return clean.strip()


# ─── whatsapp ───

def normalize_whatsapp_target(raw: str | None) -> str | None:
    if not raw:
        return None
    trimmed = raw.strip()
    if not trimmed:
        return None
    clean = strip_prefix(trimmed, "whatsapp:")
    clean = strip_prefix(clean, "wa:")
    # E.164 normalization
    digits = re.sub(r"[\s\-\(\)]+", "", clean)
    if E164_RE.match(digits):
        if not digits.startswith("+"):
            digits = f"+{digits}"
        return f"{digits}@s.whatsapp.net"
    return clean
