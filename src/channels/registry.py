"""Channels registry — ported from bk/src/channels/registry.ts.

Channel metadata definitions, ordered channel list, ID normalization,
aliases, and formatting helpers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal


# ─── types ───

@dataclass
class ChannelMeta:
    id: str = ""
    label: str = ""
    selection_label: str = ""
    detail_label: str = ""
    docs_path: str = ""
    docs_label: str = ""
    blurb: str = ""
    system_image: str = ""
    selection_docs_prefix: str = ""
    selection_docs_omit_label: bool = False
    selection_extras: list[str] = field(default_factory=list)
    order: int | None = None


# ─── channel order (canonical) ───

ChatChannelId = Literal[
    "telegram", "whatsapp", "discord", "irc", "googlechat",
    "slack", "signal", "imessage", "line",
]

CHAT_CHANNEL_ORDER: list[str] = [
    "telegram", "whatsapp", "discord", "irc", "googlechat",
    "slack", "signal", "imessage", "line",
]

CHANNEL_IDS = list(CHAT_CHANNEL_ORDER)

WEBSITE_URL = "https://openclaw.ai"

# ─── channel metadata ───

CHAT_CHANNEL_META: dict[str, ChannelMeta] = {
    "telegram": ChannelMeta(
        id="telegram", label="Telegram",
        selection_label="Telegram (Bot API)", detail_label="Telegram Bot",
        docs_path="/channels/telegram", docs_label="telegram",
        blurb="simplest way to get started — register a bot with @BotFather and get going.",
        system_image="paperplane",
        selection_docs_omit_label=True,
        selection_extras=[WEBSITE_URL],
    ),
    "whatsapp": ChannelMeta(
        id="whatsapp", label="WhatsApp",
        selection_label="WhatsApp (QR link)", detail_label="WhatsApp Web",
        docs_path="/channels/whatsapp", docs_label="whatsapp",
        blurb="works with your own number; recommend a separate phone + eSIM.",
        system_image="message",
    ),
    "discord": ChannelMeta(
        id="discord", label="Discord",
        selection_label="Discord (Bot API)", detail_label="Discord Bot",
        docs_path="/channels/discord", docs_label="discord",
        blurb="very well supported right now.",
        system_image="bubble.left.and.bubble.right",
    ),
    "irc": ChannelMeta(
        id="irc", label="IRC",
        selection_label="IRC (Server + Nick)", detail_label="IRC",
        docs_path="/channels/irc", docs_label="irc",
        blurb="classic IRC networks with DM/channel routing and pairing controls.",
        system_image="network",
    ),
    "googlechat": ChannelMeta(
        id="googlechat", label="Google Chat",
        selection_label="Google Chat (Chat API)", detail_label="Google Chat",
        docs_path="/channels/googlechat", docs_label="googlechat",
        blurb="Google Workspace Chat app with HTTP webhook.",
        system_image="message.badge",
    ),
    "slack": ChannelMeta(
        id="slack", label="Slack",
        selection_label="Slack (Socket Mode)", detail_label="Slack Bot",
        docs_path="/channels/slack", docs_label="slack",
        blurb="supported (Socket Mode).",
        system_image="number",
    ),
    "signal": ChannelMeta(
        id="signal", label="Signal",
        selection_label="Signal (signal-cli)", detail_label="Signal REST",
        docs_path="/channels/signal", docs_label="signal",
        blurb='signal-cli linked device; more setup.',
        system_image="antenna.radiowaves.left.and.right",
    ),
    "imessage": ChannelMeta(
        id="imessage", label="iMessage",
        selection_label="iMessage (imsg)", detail_label="iMessage",
        docs_path="/channels/imessage", docs_label="imessage",
        blurb="this is still a work in progress.",
        system_image="message.fill",
    ),
    "line": ChannelMeta(
        id="line", label="LINE",
        selection_label="LINE (Messaging API)", detail_label="LINE Bot",
        docs_path="/channels/line", docs_label="line",
        blurb="LINE Messaging API webhook bot.",
        system_image="message",
    ),
}

# ─── aliases ───

CHAT_CHANNEL_ALIASES: dict[str, str] = {
    "imsg": "imessage",
    "internet-relay-chat": "irc",
    "google-chat": "googlechat",
    "gchat": "googlechat",
}


# ─── functions ───

def _normalize_channel_key(raw: str | None) -> str | None:
    if not raw:
        return None
    normalized = raw.strip().lower()
    return normalized or None


def list_chat_channels() -> list[ChannelMeta]:
    """Return ordered list of all chat channel metadata."""
    return [CHAT_CHANNEL_META[ch] for ch in CHAT_CHANNEL_ORDER if ch in CHAT_CHANNEL_META]


def list_chat_channel_aliases() -> list[str]:
    return list(CHAT_CHANNEL_ALIASES.keys())


def get_chat_channel_meta(channel_id: str) -> ChannelMeta | None:
    return CHAT_CHANNEL_META.get(channel_id)


def normalize_chat_channel_id(raw: str | None) -> str | None:
    """Normalize a channel ID string, resolving aliases."""
    normalized = _normalize_channel_key(raw)
    if not normalized:
        return None
    resolved = CHAT_CHANNEL_ALIASES.get(normalized, normalized)
    return resolved if resolved in CHAT_CHANNEL_ORDER else None


def normalize_channel_id(raw: str | None) -> str | None:
    """Alias for normalize_chat_channel_id for shared code."""
    return normalize_chat_channel_id(raw)


def format_channel_primer_line(meta: ChannelMeta) -> str:
    return f"{meta.label}: {meta.blurb}"


def format_channel_selection_line(
    meta: ChannelMeta,
    docs_link: Callable[[str, str | None], str] | None = None,
) -> str:
    """Format a channel selection line with optional docs link."""
    docs_prefix = meta.selection_docs_prefix or "Docs:"
    docs_label = meta.docs_label or meta.id

    if docs_link:
        if meta.selection_docs_omit_label:
            docs = docs_link(meta.docs_path, None)
        else:
            docs = docs_link(meta.docs_path, docs_label)
    else:
        docs = meta.docs_path

    extras = " ".join(e for e in meta.selection_extras if e)
    parts = [f"{meta.label} — {meta.blurb}"]
    if docs_prefix:
        parts.append(f"{docs_prefix} {docs}")
    else:
        parts.append(docs)
    if extras:
        parts.append(extras)
    return " ".join(parts)
