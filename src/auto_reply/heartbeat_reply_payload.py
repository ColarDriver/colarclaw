"""Auto-reply heartbeat reply payload — ported from bk/src/auto-reply/heartbeat-reply-payload.ts."""
from __future__ import annotations

from .types import ReplyPayload


def resolve_heartbeat_reply_payload(
    reply_result: ReplyPayload | list[ReplyPayload] | None,
) -> ReplyPayload | None:
    if reply_result is None:
        return None
    if not isinstance(reply_result, list):
        return reply_result
    for payload in reversed(reply_result):
        if payload.text or payload.media_url or (payload.media_urls and len(payload.media_urls) > 0):
            return payload
    return None
