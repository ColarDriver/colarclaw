"""ACP conversation ID — ported from bk/src/acp/conversation-id.ts.

Telegram topic conversation ID parsing and formatting.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ParsedTelegramTopicConversation:
    chat_id: str
    topic_id: str
    canonical_conversation_id: str


def _normalize_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value).strip()
    return ""


def parse_telegram_chat_id_from_target(raw: object) -> str | None:
    text = _normalize_text(raw)
    if not text:
        return None
    match = re.match(r"^telegram:(-?\d+)$", text)
    return match.group(1) if match else None


def build_telegram_topic_conversation_id(chat_id: str, topic_id: str) -> str | None:
    cid = chat_id.strip()
    tid = topic_id.strip()
    if not re.match(r"^-?\d+$", cid) or not re.match(r"^\d+$", tid):
        return None
    return f"{cid}:topic:{tid}"


def parse_telegram_topic_conversation(
    conversation_id: str,
    parent_conversation_id: str | None = None,
) -> ParsedTelegramTopicConversation | None:
    conv = conversation_id.strip()
    direct = re.match(r"^(-?\d+):topic:(\d+)$", conv)
    if direct:
        cid = build_telegram_topic_conversation_id(direct.group(1), direct.group(2))
        if not cid:
            return None
        return ParsedTelegramTopicConversation(
            chat_id=direct.group(1), topic_id=direct.group(2),
            canonical_conversation_id=cid,
        )
    if not re.match(r"^\d+$", conv):
        return None
    parent = (parent_conversation_id or "").strip()
    if not parent or not re.match(r"^-?\d+$", parent):
        return None
    cid = build_telegram_topic_conversation_id(parent, conv)
    if not cid:
        return None
    return ParsedTelegramTopicConversation(
        chat_id=parent, topic_id=conv,
        canonical_conversation_id=cid,
    )
