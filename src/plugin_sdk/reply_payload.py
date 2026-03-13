"""Plugin SDK reply payload — ported from bk/src/plugin-sdk/reply-payload.ts.

Outbound reply payload normalization, chunked text + media delivery, attachment linking.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine


@dataclass
class OutboundReplyPayload:
    text: str | None = None
    media_urls: list[str] | None = None
    media_url: str | None = None
    reply_to_id: str | None = None


def normalize_outbound_reply_payload(payload: dict[str, Any]) -> OutboundReplyPayload:
    text = payload.get("text") if isinstance(payload.get("text"), str) else None
    raw_urls = payload.get("mediaUrls") or payload.get("media_urls")
    media_urls = [e for e in raw_urls if isinstance(e, str) and e] if isinstance(raw_urls, list) else None
    media_url = payload.get("mediaUrl") or payload.get("media_url")
    media_url = media_url if isinstance(media_url, str) else None
    reply_to_id = payload.get("replyToId") or payload.get("reply_to_id")
    reply_to_id = reply_to_id if isinstance(reply_to_id, str) else None
    return OutboundReplyPayload(text=text, media_urls=media_urls, media_url=media_url, reply_to_id=reply_to_id)


def create_normalized_outbound_deliverer(handler: Callable[..., Any]) -> Callable[..., Any]:
    async def deliver(payload: Any) -> None:
        normalized = normalize_outbound_reply_payload(payload) if isinstance(payload, dict) else OutboundReplyPayload()
        await handler(normalized)
    return deliver


def resolve_outbound_media_urls(payload: OutboundReplyPayload | dict[str, Any]) -> list[str]:
    if isinstance(payload, dict):
        urls = payload.get("media_urls") or payload.get("mediaUrls")
        url = payload.get("media_url") or payload.get("mediaUrl")
    else:
        urls = payload.media_urls
        url = payload.media_url
    if urls:
        return list(urls)
    if url:
        return [url]
    return []


async def send_payload_with_chunked_text_and_media(
    ctx: Any,
    send_text: Callable[..., Any],
    send_media: Callable[..., Any],
    empty_result: Any = None,
    text_chunk_limit: int | None = None,
    chunker: Callable[[str, int], list[str]] | None = None,
) -> Any:
    payload = getattr(ctx, "payload", ctx) if not isinstance(ctx, dict) else ctx
    text = (payload.get("text") or "") if isinstance(payload, dict) else (getattr(payload, "text", "") or "")
    urls = resolve_outbound_media_urls(payload)
    if not text and not urls:
        return empty_result
    if urls:
        last_result = await send_media(text=text, media_url=urls[0])
        for url in urls[1:]:
            last_result = await send_media(text="", media_url=url)
        return last_result
    chunks = chunker(text, text_chunk_limit) if text_chunk_limit and chunker else [text]
    last_result = empty_result
    for chunk in chunks:
        last_result = await send_text(text=chunk)
    return last_result


def is_numeric_target_id(raw: str) -> bool:
    trimmed = raw.strip()
    return bool(re.match(r"^\d{3,}$", trimmed)) if trimmed else False


def format_text_with_attachment_links(text: str | None, media_urls: list[str]) -> str:
    trimmed = (text or "").strip()
    if not trimmed and not media_urls:
        return ""
    media_block = "\n".join(f"Attachment: {url}" for url in media_urls) if media_urls else ""
    if not trimmed:
        return media_block
    if not media_block:
        return trimmed
    return f"{trimmed}\n\n{media_block}"


async def send_media_with_leading_caption(
    media_urls: list[str],
    caption: str,
    send: Callable[..., Any],
    on_error: Callable[..., None] | None = None,
) -> bool:
    if not media_urls:
        return False
    first = True
    for url in media_urls:
        cap = caption if first else None
        first = False
        try:
            await send(media_url=url, caption=cap)
        except Exception as e:
            if on_error:
                on_error(e, url)
                continue
            raise
    return True
