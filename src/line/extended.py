"""LINE — extended: webhook events, rich menu, Flex Carousel, delivery.

Ported from remaining bk/src/line/ files (~30 TS, ~6k lines).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── Webhook signature verification ───

def verify_webhook_signature(body: bytes, signature: str, channel_secret: str) -> bool:
    """Verify LINE webhook signature."""
    expected = hmac.new(
        channel_secret.encode("utf-8"), body, hashlib.sha256
    ).digest()
    import base64
    expected_b64 = base64.b64encode(expected).decode("ascii")
    return hmac.compare_digest(signature, expected_b64)


# ─── Webhook events ───

@dataclass
class LineEvent:
    type: str = ""  # "message" | "follow" | "unfollow" | "join" | "leave" | "postback"
    reply_token: str = ""
    source_type: str = ""
    source_id: str = ""
    user_id: str = ""
    timestamp: int = 0
    message: dict[str, Any] = field(default_factory=dict)
    postback_data: str = ""


def parse_webhook_events(body: dict[str, Any]) -> list[LineEvent]:
    """Parse LINE webhook request body into events."""
    events = []
    for raw in body.get("events", []):
        source = raw.get("source", {})
        events.append(LineEvent(
            type=raw.get("type", ""),
            reply_token=raw.get("replyToken", ""),
            source_type=source.get("type", ""),
            source_id=source.get("groupId") or source.get("roomId") or source.get("userId", ""),
            user_id=source.get("userId", ""),
            timestamp=int(raw.get("timestamp", 0)),
            message=raw.get("message", {}),
            postback_data=raw.get("postback", {}).get("data", ""),
        ))
    return events


# ─── Rich menu ───

@dataclass
class RichMenuArea:
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    action_type: str = "message"
    action_data: str = ""
    label: str = ""


def build_rich_menu(
    name: str,
    chat_bar_text: str,
    areas: list[RichMenuArea],
    *,
    size_width: int = 2500,
    size_height: int = 843,
    selected: bool = False,
) -> dict[str, Any]:
    """Build a LINE rich menu object."""
    return {
        "size": {"width": size_width, "height": size_height},
        "selected": selected,
        "name": name,
        "chatBarText": chat_bar_text,
        "areas": [
            {
                "bounds": {"x": a.x, "y": a.y, "width": a.width, "height": a.height},
                "action": {
                    "type": a.action_type,
                    "label": a.label[:20],
                    "text" if a.action_type == "message" else "data": a.action_data,
                },
            }
            for a in areas
        ],
    }


# ─── Flex Carousel ───

def build_flex_carousel(bubbles: list[dict[str, Any]], *, alt_text: str = "Carousel") -> dict[str, Any]:
    """Build a LINE Flex Message carousel container."""
    return {
        "type": "flex",
        "altText": alt_text[:400],
        "contents": {
            "type": "carousel",
            "contents": bubbles[:12],
        },
    }


# ─── Delivery ───

async def deliver_line_reply(
    adapter: Any, *,
    reply_token: str | None = None,
    to: str | None = None,
    text: str = "",
    quick_reply_items: list[dict[str, str]] | None = None,
) -> bool:
    """Deliver a reply via LINE — reply API (free) or push API."""
    from . import build_quick_reply
    qr = build_quick_reply(quick_reply_items) if quick_reply_items else None
    
    if reply_token:
        messages: list[dict[str, Any]] = [{"type": "text", "text": text[:5000]}]
        if qr:
            messages[0]["quickReply"] = qr
        return await adapter.reply(reply_token, messages)
    elif to:
        return await adapter.send_text(to, text, quick_reply=qr)
    return False


# ─── Postback handler ───

def parse_postback_data(data: str) -> dict[str, str]:
    """Parse LINE postback data (key=value&key2=value2)."""
    result: dict[str, str] = {}
    for pair in data.split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            result[k] = v
    return result
