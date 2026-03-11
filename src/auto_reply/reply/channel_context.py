"""Reply channel context — ported from bk/src/auto-reply/reply/channel-context.ts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ChannelReplyContext:
    channel: str = ""
    account_id: str | None = None
    chat_id: str | None = None
    thread_id: str | None = None
    is_group: bool = False
    is_thread: bool = False


def resolve_channel_context(ctx: Any) -> ChannelReplyContext:
    return ChannelReplyContext(
        channel=getattr(ctx, "Provider", "") or getattr(ctx, "Surface", "") or "",
        account_id=getattr(ctx, "AccountId", None),
        chat_id=getattr(ctx, "ChatId", None) or getattr(ctx, "From", None),
        thread_id=getattr(ctx, "ThreadId", None),
        is_group=bool(getattr(ctx, "ChatType", "") and getattr(ctx, "ChatType", "").strip().lower() != "direct"),
        is_thread=bool(getattr(ctx, "ThreadId", None)),
    )
