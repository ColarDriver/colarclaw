"""Channels plugins.group_mentions — ported from bk/src/channels/plugins/group-mentions.ts.

Per-channel group mention policy resolution: requireMention and tool policy
for Telegram, WhatsApp, Discord, Slack, iMessage, Google Chat, LINE, BlueBubbles.
"""
from __future__ import annotations

import re
from typing import Any


# ─── slug normalization ───

def normalize_at_hash_slug(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip().lower()
    cleaned = re.sub(r"^[@#]+", "", cleaned)
    cleaned = re.sub(r"[^a-z0-9-]+", "-", cleaned).strip("-")
    return cleaned or None


def normalize_hyphen_slug(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip().lower()
    cleaned = re.sub(r"[^a-z0-9-]+", "-", cleaned).strip("-")
    return cleaned or None


# ─── Telegram group ID parsing ───

def parse_telegram_group_id(value: str | None) -> tuple[str | None, str | None]:
    """Parse Telegram group ID into (chatId, topicId)."""
    raw = (value or "").strip()
    if not raw:
        return None, None
    parts = [p for p in raw.split(":") if p]
    if (
        len(parts) >= 3 and parts[1] == "topic"
        and re.match(r"^-?\d+$", parts[0])
        and re.match(r"^\d+$", parts[2])
    ):
        return parts[0], parts[2]
    if len(parts) >= 2 and re.match(r"^-?\d+$", parts[0]) and re.match(r"^\d+$", parts[1]):
        return parts[0], parts[1]
    return raw, None


# ─── generic channel requireMention ───

def resolve_channel_group_require_mention(
    cfg: dict[str, Any],
    channel: str,
    group_id: str | None = None,
    account_id: str | None = None,
) -> bool:
    """Resolve requireMention from channel groups config."""
    channels_cfg = cfg.get("channels", {})
    channel_cfg = channels_cfg.get(channel, {})
    groups = channel_cfg.get("groups", {})

    if group_id and group_id in groups:
        entry = groups[group_id]
        if isinstance(entry, dict) and isinstance(entry.get("requireMention"), bool):
            return entry["requireMention"]

    wildcard = groups.get("*", {})
    if isinstance(wildcard, dict) and isinstance(wildcard.get("requireMention"), bool):
        return wildcard["requireMention"]

    return True


# ─── generic channel tool policy ───

def resolve_channel_group_tools_policy(
    cfg: dict[str, Any],
    channel: str,
    group_id: str | None = None,
    sender_id: str | None = None,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """Resolve tool policy from channel groups config."""
    channels_cfg = cfg.get("channels", {})
    channel_cfg = channels_cfg.get(channel, {})
    groups = channel_cfg.get("groups", {})

    entry = None
    if group_id and group_id in groups:
        entry = groups[group_id]
    elif "*" in groups:
        entry = groups["*"]

    if not entry or not isinstance(entry, dict):
        return None

    # Check sender-specific tools
    tools_by_sender = entry.get("toolsBySender", {})
    if sender_id and isinstance(tools_by_sender, dict):
        for key, policy in tools_by_sender.items():
            if sender_id.lower() == key.lower():
                return policy

    return entry.get("tools")


# ─── Telegram ───

def resolve_telegram_group_require_mention(
    cfg: dict[str, Any],
    group_id: str | None = None,
    **kwargs: Any,
) -> bool | None:
    """Resolve Telegram group requireMention with topic support."""
    chat_id, topic_id = parse_telegram_group_id(group_id)
    if not chat_id:
        return None

    tg_cfg = cfg.get("channels", {}).get("telegram", {})
    groups = tg_cfg.get("groups", {})

    group_config = groups.get(chat_id, {}) if isinstance(groups, dict) else {}
    group_default = groups.get("*", {}) if isinstance(groups, dict) else {}

    # Check topic config first
    if topic_id:
        topic_cfg = group_config.get("topics", {}).get(topic_id, {}) if isinstance(group_config, dict) else {}
        if isinstance(topic_cfg, dict) and isinstance(topic_cfg.get("requireMention"), bool):
            return topic_cfg["requireMention"]
        default_topic_cfg = group_default.get("topics", {}).get(topic_id, {}) if isinstance(group_default, dict) else {}
        if isinstance(default_topic_cfg, dict) and isinstance(default_topic_cfg.get("requireMention"), bool):
            return default_topic_cfg["requireMention"]

    if isinstance(group_config, dict) and isinstance(group_config.get("requireMention"), bool):
        return group_config["requireMention"]
    if isinstance(group_default, dict) and isinstance(group_default.get("requireMention"), bool):
        return group_default["requireMention"]

    return resolve_channel_group_require_mention(cfg, "telegram", chat_id)


def resolve_telegram_group_tool_policy(
    cfg: dict[str, Any],
    group_id: str | None = None,
    **kwargs: Any,
) -> dict[str, Any] | None:
    chat_id, _ = parse_telegram_group_id(group_id)
    return resolve_channel_group_tools_policy(cfg, "telegram", chat_id or group_id, **kwargs)


# ─── WhatsApp ───

def resolve_whatsapp_group_require_mention(cfg: dict[str, Any], **kwargs: Any) -> bool:
    return resolve_channel_group_require_mention(cfg, "whatsapp", kwargs.get("group_id"))


def resolve_whatsapp_group_tool_policy(cfg: dict[str, Any], **kwargs: Any) -> dict[str, Any] | None:
    return resolve_channel_group_tools_policy(cfg, "whatsapp", **kwargs)


# ─── iMessage ───

def resolve_imessage_group_require_mention(cfg: dict[str, Any], **kwargs: Any) -> bool:
    return resolve_channel_group_require_mention(cfg, "imessage", kwargs.get("group_id"))


def resolve_imessage_group_tool_policy(cfg: dict[str, Any], **kwargs: Any) -> dict[str, Any] | None:
    return resolve_channel_group_tools_policy(cfg, "imessage", **kwargs)


# ─── Discord ───

def _resolve_discord_guild_entry(
    guilds: dict[str, Any] | None,
    group_space: str | None = None,
) -> dict[str, Any] | None:
    if not guilds:
        return None
    space = (group_space or "").strip()
    if space and space in guilds:
        return guilds[space]
    normalized = normalize_at_hash_slug(space)
    if normalized and normalized in guilds:
        return guilds[normalized]
    if normalized:
        for entry in guilds.values():
            if isinstance(entry, dict):
                slug_norm = normalize_at_hash_slug(entry.get("slug"))
                if slug_norm == normalized:
                    return entry
    return guilds.get("*")


def _resolve_discord_channel_entry(
    channel_entries: dict[str, Any] | None,
    group_id: str | None = None,
    group_channel: str | None = None,
) -> dict[str, Any] | None:
    if not channel_entries:
        return None
    slug = normalize_at_hash_slug(group_channel)
    candidates = [
        group_id,
        slug,
        f"#{slug}" if slug else None,
        normalize_at_hash_slug(group_channel) if group_channel else None,
    ]
    for c in candidates:
        if c and c in channel_entries:
            return channel_entries[c]
    return None


def resolve_discord_group_require_mention(
    cfg: dict[str, Any],
    group_space: str | None = None,
    group_id: str | None = None,
    group_channel: str | None = None,
    **kwargs: Any,
) -> bool:
    discord_cfg = cfg.get("channels", {}).get("discord", {})
    guild = _resolve_discord_guild_entry(discord_cfg.get("guilds"), group_space)
    if guild:
        ch_entry = _resolve_discord_channel_entry(
            guild.get("channels"), group_id, group_channel,
        )
        if isinstance(ch_entry, dict) and isinstance(ch_entry.get("requireMention"), bool):
            return ch_entry["requireMention"]
        if isinstance(guild.get("requireMention"), bool):
            return guild["requireMention"]
    return True


def resolve_discord_group_tool_policy(
    cfg: dict[str, Any],
    group_space: str | None = None,
    group_id: str | None = None,
    group_channel: str | None = None,
    **kwargs: Any,
) -> dict[str, Any] | None:
    discord_cfg = cfg.get("channels", {}).get("discord", {})
    guild = _resolve_discord_guild_entry(discord_cfg.get("guilds"), group_space)
    if not guild:
        return None
    ch_entry = _resolve_discord_channel_entry(
        guild.get("channels"), group_id, group_channel,
    )
    if isinstance(ch_entry, dict) and ch_entry.get("tools"):
        return ch_entry["tools"]
    return guild.get("tools") if isinstance(guild, dict) else None


# ─── Slack ───

def resolve_slack_group_require_mention(
    cfg: dict[str, Any],
    account_id: str | None = None,
    group_id: str | None = None,
    group_channel: str | None = None,
    **kwargs: Any,
) -> bool:
    slack_cfg = cfg.get("channels", {}).get("slack", {})
    # Check account-level channels
    acct_cfg = slack_cfg
    if account_id:
        acct_cfg = slack_cfg.get("accounts", {}).get(account_id, slack_cfg)
    channels = acct_cfg.get("channels", {})
    if not channels:
        return True
    channel_name = (group_channel or "").lstrip("#")
    norm = normalize_hyphen_slug(channel_name)
    candidates = [
        group_id or "",
        f"#{channel_name}" if channel_name else "",
        channel_name,
        norm or "",
    ]
    for c in (c for c in candidates if c):
        if c in channels:
            entry = channels[c]
            if isinstance(entry, dict) and isinstance(entry.get("requireMention"), bool):
                return entry["requireMention"]
    wildcard = channels.get("*", {})
    if isinstance(wildcard, dict) and isinstance(wildcard.get("requireMention"), bool):
        return wildcard["requireMention"]
    return True


def resolve_slack_group_tool_policy(cfg: dict[str, Any], **kwargs: Any) -> dict[str, Any] | None:
    return resolve_channel_group_tools_policy(cfg, "slack", **kwargs)


# ─── Google Chat ───

def resolve_googlechat_group_require_mention(cfg: dict[str, Any], **kwargs: Any) -> bool:
    return resolve_channel_group_require_mention(cfg, "googlechat", kwargs.get("group_id"))


def resolve_googlechat_group_tool_policy(cfg: dict[str, Any], **kwargs: Any) -> dict[str, Any] | None:
    return resolve_channel_group_tools_policy(cfg, "googlechat", **kwargs)


# ─── LINE ───

def resolve_line_group_require_mention(cfg: dict[str, Any], **kwargs: Any) -> bool:
    return resolve_channel_group_require_mention(cfg, "line", kwargs.get("group_id"))


def resolve_line_group_tool_policy(cfg: dict[str, Any], **kwargs: Any) -> dict[str, Any] | None:
    return resolve_channel_group_tools_policy(cfg, "line", **kwargs)


# ─── BlueBubbles ───

def resolve_bluebubbles_group_require_mention(cfg: dict[str, Any], **kwargs: Any) -> bool:
    return resolve_channel_group_require_mention(cfg, "bluebubbles", kwargs.get("group_id"))


def resolve_bluebubbles_group_tool_policy(cfg: dict[str, Any], **kwargs: Any) -> dict[str, Any] | None:
    return resolve_channel_group_tools_policy(cfg, "bluebubbles", **kwargs)
