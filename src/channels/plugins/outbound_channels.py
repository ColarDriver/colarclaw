"""Channels plugins.outbound_channels — ported from bk/src/channels/plugins/outbound/{telegram,discord,slack,whatsapp,signal,imessage}.ts.

Per-channel outbound message adapters for constructing and sending
messages via each channel's API.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("channels.plugins.outbound_channels")


# ─── shared types ───

@dataclass
class OutboundSendPayload:
    to: str = ""
    text: str = ""
    media_url: str | None = None
    media_path: str | None = None
    thread_id: str | None = None
    reply_to_id: str | None = None
    silent: bool = False
    buttons: list[dict[str, str]] | None = None


@dataclass
class OutboundSendResult:
    message_id: str = ""
    channel_id: str = ""
    conversation_id: str = ""
    thread_id: str = ""
    error: str | None = None


# ─── Telegram outbound ───

class TelegramOutboundAdapter:
    channel = "telegram"
    max_text_length = 4096

    @staticmethod
    def build_send_payload(
        to: str,
        text: str,
        media_url: str | None = None,
        parse_mode: str = "MarkdownV2",
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"chat_id": to, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if media_url:
            payload["photo"] = media_url
        if kwargs.get("reply_to_message_id"):
            payload["reply_to_message_id"] = kwargs["reply_to_message_id"]
        if kwargs.get("silent"):
            payload["disable_notification"] = True
        return payload

    @staticmethod
    def chunk_text(text: str, max_len: int = 4096) -> list[str]:
        if len(text) <= max_len:
            return [text]
        chunks = []
        while text:
            if len(text) <= max_len:
                chunks.append(text)
                break
            split = text.rfind("\n", 0, max_len)
            if split <= 0:
                split = max_len
            chunks.append(text[:split])
            text = text[split:].lstrip("\n")
        return chunks


# ─── Discord outbound ───

class DiscordOutboundAdapter:
    channel = "discord"
    max_text_length = 2000

    @staticmethod
    def build_send_payload(
        to: str,
        text: str,
        thread_id: str | None = None,
        reply_to_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"content": text}
        if reply_to_id:
            payload["message_reference"] = {"message_id": reply_to_id}
        return payload

    @staticmethod
    def chunk_text(text: str, max_len: int = 2000) -> list[str]:
        if len(text) <= max_len:
            return [text]
        chunks = []
        while text:
            if len(text) <= max_len:
                chunks.append(text)
                break
            # Try to split at code block boundary
            split = text.rfind("```", 0, max_len)
            if split <= 0:
                split = text.rfind("\n", 0, max_len)
            if split <= 0:
                split = max_len
            chunks.append(text[:split])
            text = text[split:]
        return chunks


# ─── Slack outbound ───

class SlackOutboundAdapter:
    channel = "slack"
    max_text_length = 4000

    @staticmethod
    def build_send_payload(
        to: str,
        text: str,
        thread_ts: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "channel": to,
            "text": text,
        }
        if thread_ts:
            payload["thread_ts"] = thread_ts
        return payload

    @staticmethod
    def build_blocks(text: str) -> list[dict[str, Any]]:
        return [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]


# ─── WhatsApp outbound ───

class WhatsAppOutboundAdapter:
    channel = "whatsapp"
    max_text_length = 4096

    @staticmethod
    def build_send_payload(
        to: str,
        text: str,
        media_url: str | None = None,
        quoted_msg_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"to": to}
        if media_url:
            payload["type"] = "image"
            payload["image"] = {"url": media_url, "caption": text}
        else:
            payload["type"] = "text"
            payload["text"] = text
        if quoted_msg_id:
            payload["quotedMsgId"] = quoted_msg_id
        return payload


# ─── Signal outbound ───

class SignalOutboundAdapter:
    channel = "signal"
    max_text_length = 4096

    @staticmethod
    def build_send_payload(
        to: str,
        text: str,
        attachments: list[str] | None = None,
        quote_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "recipients": [to],
            "message": text,
        }
        if attachments:
            payload["base64_attachments"] = attachments
        if quote_id:
            payload["quote_id"] = quote_id
        return payload


# ─── iMessage outbound ───

class IMessageOutboundAdapter:
    channel = "imessage"
    max_text_length = 4096

    @staticmethod
    def build_send_payload(
        to: str,
        text: str,
        service: str = "iMessage",
        **kwargs: Any,
    ) -> dict[str, Any]:
        return {
            "handle": to,
            "text": text,
            "service": service,
        }


# ─── adapter registry ───

OUTBOUND_ADAPTERS: dict[str, Any] = {
    "telegram": TelegramOutboundAdapter,
    "discord": DiscordOutboundAdapter,
    "slack": SlackOutboundAdapter,
    "whatsapp": WhatsAppOutboundAdapter,
    "signal": SignalOutboundAdapter,
    "imessage": IMessageOutboundAdapter,
}


def get_outbound_adapter(channel: str) -> Any | None:
    return OUTBOUND_ADAPTERS.get(channel)
