"""Reply body — ported from bk/src/auto-reply/reply/body.ts."""
from __future__ import annotations

from typing import Any


def build_reply_body(
    text: str,
    media_urls: list[str] | None = None,
    tool_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"text": text}
    if media_urls:
        body["media_urls"] = media_urls
    if tool_results:
        body["tool_results"] = tool_results
    return body


def format_reply_text(text: str, max_length: int | None = None) -> str:
    if not text:
        return ""
    result = text.strip()
    if max_length and len(result) > max_length:
        return result[:max_length - 3].rstrip() + "..."
    return result
