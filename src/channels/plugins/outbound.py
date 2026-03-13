"""Channels plugins.outbound — ported from bk/src/channels/plugins/outbound/*.ts.

Channel-specific outbound message adapters for sending text/media
to each channel's API.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Protocol

logger = logging.getLogger("channels.plugins.outbound")


# ─── outbound/load.ts ───

async def load_channel_outbound_adapter(channel_id: str) -> Any | None:
    """Load the outbound adapter for a specific channel.

    Returns None if no adapter is registered for this channel.
    In the TS version this is a dynamic import; here we use registry lookup.
    """
    from .catalog import get_active_plugin_registry
    registry = get_active_plugin_registry()
    if not registry:
        return None
    entry = registry.get(channel_id)
    if not entry or not entry.plugin.outbound:
        return None
    return entry.plugin.outbound


# ─── outbound/direct-text-media.ts (summary) ───

@dataclass
class DirectTextMediaResult:
    message_id: str = ""
    channel_id: str = ""
    conversation_id: str = ""


async def send_direct_text_media(
    send_fn: Callable,
    to: str,
    text: str,
    media_url: str | None = None,
    **kwargs: Any,
) -> DirectTextMediaResult:
    """Send text+media via a channel's send function."""
    try:
        result = await send_fn(to=to, text=text, media_url=media_url, **kwargs)
        if isinstance(result, dict):
            return DirectTextMediaResult(
                message_id=result.get("messageId", ""),
                channel_id=result.get("channelId", ""),
                conversation_id=result.get("conversationId", ""),
            )
        return DirectTextMediaResult()
    except Exception as e:
        logger.error(f"send_direct_text_media error: {e}")
        raise
