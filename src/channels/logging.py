"""Channels logging — ported from bk/src/channels/logging.ts.

Channel-scoped logging utilities.
"""
from __future__ import annotations

import logging


def create_channel_logger(channel: str, account_id: str = "") -> logging.Logger:
    """Create a logger scoped to a specific channel and account."""
    name = f"channels.{channel}"
    if account_id:
        name += f".{account_id}"
    return logging.getLogger(name)


def log_channel_event(
    channel: str,
    event: str,
    account_id: str = "",
    **kwargs: object,
) -> None:
    """Log a channel event at INFO level."""
    logger = create_channel_logger(channel, account_id)
    extra = " ".join(f"{k}={v}" for k, v in kwargs.items())
    logger.info(f"[{event}] {extra}" if extra else f"[{event}]")
