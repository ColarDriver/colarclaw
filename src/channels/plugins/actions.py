"""Channels plugins.actions — ported from bk/src/channels/plugins/actions/*.ts.

Channel-specific message action implementations (reactions, emoji, etc.)
and shared action utilities.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("channels.plugins.actions")


# ─── shared ───

@dataclass
class ActionResult:
    success: bool = True
    message_id: str = ""
    error: str = ""


def validate_action_target(to: str | None) -> str:
    """Validate and normalize an action target ID."""
    if not to or not to.strip():
        raise ValueError("action target (to) is required")
    return to.strip()


# ─── reaction-message-id.ts ───

def resolve_reaction_message_id(
    reply_to_id: str | None = None,
    current_message_id: str | None = None,
) -> str | None:
    """Resolve which message ID to react to."""
    if reply_to_id and reply_to_id.strip():
        return reply_to_id.strip()
    if current_message_id and current_message_id.strip():
        return current_message_id.strip()
    return None


# ─── channel action dispatch ───

async def dispatch_channel_action(
    channel: str,
    action: str,
    params: dict[str, Any],
    account_id: str = "",
) -> ActionResult:
    """Dispatch an action to a specific channel's handler.

    This is a simplified version — the full TS implementation
    loads per-channel action handlers dynamically.
    """
    from .catalog import get_active_plugin_registry
    registry = get_active_plugin_registry()
    if not registry:
        return ActionResult(success=False, error="plugin registry not initialized")

    entry = registry.get(channel)
    if not entry:
        return ActionResult(success=False, error=f"channel {channel} not found")

    if not entry.plugin.message_actions:
        return ActionResult(success=False, error=f"channel {channel} has no message actions")

    handler = entry.plugin.message_actions.get("handleAction")
    if not handler:
        return ActionResult(success=False, error=f"no action handler for {channel}")

    try:
        result = await handler(action=action, params=params, account_id=account_id)
        return ActionResult(success=True, message_id=str(result) if result else "")
    except Exception as e:
        return ActionResult(success=False, error=str(e))
