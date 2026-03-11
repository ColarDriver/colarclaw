"""Auto-reply heartbeat — ported from bk/src/auto-reply/heartbeat.ts."""
from __future__ import annotations

import re
from typing import Literal

HEARTBEAT_TOKEN = "HEARTBEAT_OK"
HEARTBEAT_PROMPT = (
    "Read HEARTBEAT.md if it exists (workspace context). Follow it strictly. "
    "Do not infer or repeat old tasks from prior chats. "
    "If nothing needs attention, reply HEARTBEAT_OK."
)
DEFAULT_HEARTBEAT_EVERY = "30m"
DEFAULT_HEARTBEAT_ACK_MAX_CHARS = 300

StripHeartbeatMode = Literal["heartbeat", "message"]


def is_heartbeat_content_effectively_empty(content: str | None) -> bool:
    if content is None:
        return False
    if not isinstance(content, str):
        return False
    for line in content.split("\n"):
        trimmed = line.strip()
        if not trimmed:
            continue
        if re.match(r"^#+(\\s|$)", trimmed):
            continue
        if re.match(r"^[-*+]\s*(\[[\sXx]?\]\s*)?$", trimmed):
            continue
        return False
    return True


def resolve_heartbeat_prompt(raw: str | None = None) -> str:
    trimmed = (raw or "").strip()
    return trimmed or HEARTBEAT_PROMPT


def _strip_token_at_edges(raw: str) -> tuple[str, bool]:
    text = raw.strip()
    if not text:
        return "", False
    if HEARTBEAT_TOKEN not in text:
        return text, False

    did_strip = False
    changed = True
    while changed:
        changed = False
        text = text.strip()
        if text.startswith(HEARTBEAT_TOKEN):
            text = text[len(HEARTBEAT_TOKEN):].lstrip()
            did_strip = True
            changed = True
            continue
        pattern = re.compile(re.escape(HEARTBEAT_TOKEN) + r"[^\w]{0,4}$")
        if pattern.search(text):
            idx = text.rfind(HEARTBEAT_TOKEN)
            before = text[:idx].rstrip()
            if not before:
                text = ""
            else:
                after = text[idx + len(HEARTBEAT_TOKEN):].lstrip()
                text = f"{before}{after}".rstrip()
            did_strip = True
            changed = True

    collapsed = re.sub(r"\s+", " ", text).strip()
    return collapsed, did_strip


def strip_heartbeat_token(
    raw: str | None = None,
    mode: StripHeartbeatMode = "message",
    max_ack_chars: int | None = None,
) -> dict[str, bool | str]:
    if not raw:
        return {"should_skip": True, "text": "", "did_strip": False}
    trimmed = raw.strip()
    if not trimmed:
        return {"should_skip": True, "text": "", "did_strip": False}

    effective_max = max_ack_chars if isinstance(max_ack_chars, int) else DEFAULT_HEARTBEAT_ACK_MAX_CHARS
    effective_max = max(0, effective_max)

    stripped_markup = re.sub(r"<[^>]*>", " ", trimmed)
    stripped_markup = re.sub(r"&nbsp;", " ", stripped_markup, flags=re.IGNORECASE)
    stripped_markup = re.sub(r"^[*`~_]+", "", stripped_markup)
    stripped_markup = re.sub(r"[*`~_]+$", "", stripped_markup)

    has_token = HEARTBEAT_TOKEN in trimmed or HEARTBEAT_TOKEN in stripped_markup
    if not has_token:
        return {"should_skip": False, "text": trimmed, "did_strip": False}

    text_orig, did_orig = _strip_token_at_edges(trimmed)
    text_norm, did_norm = _strip_token_at_edges(stripped_markup)
    picked_text, picked_did = (text_orig, did_orig) if did_orig and text_orig else (text_norm, did_norm)

    if not picked_did:
        return {"should_skip": False, "text": trimmed, "did_strip": False}
    if not picked_text:
        return {"should_skip": True, "text": "", "did_strip": True}

    rest = picked_text.strip()
    if mode == "heartbeat" and len(rest) <= effective_max:
        return {"should_skip": True, "text": "", "did_strip": True}
    return {"should_skip": False, "text": rest, "did_strip": True}
