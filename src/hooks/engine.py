"""Hooks system — ported from bk/src/hooks/internal-hooks.ts.

Event-driven hook system for agent lifecycle events:
- command: CLI command events
- session: session lifecycle
- agent: agent bootstrap
- gateway: gateway startup
- message: message received/sent/transcribed/preprocessed

Handlers are registered by event key (type or type:action) and
triggered in registration order. Errors are caught and logged.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Literal, Union

log = logging.getLogger("openclaw.hooks")

HookEventType = Literal["command", "session", "agent", "gateway", "message"]
HookHandler = Callable[["HookEvent"], Union[Awaitable[None], None]]


@dataclass
class HookEvent:
    """Base hook event."""
    type: HookEventType
    action: str
    session_key: str
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    messages: list[str] = field(default_factory=list)


# ── Global handler registry ───────────────────────────────────────────────
_handlers: dict[str, list[HookHandler]] = {}


def register_hook(event_key: str, handler: HookHandler) -> None:
    """Register a hook handler for a specific event type or event:action.

    Args:
        event_key: Event type (e.g., 'command') or specific action (e.g., 'command:new')
        handler: Function to call when the event is triggered

    Example:
        register_hook('command', handle_all_commands)
        register_hook('command:new', handle_new_command)
    """
    if event_key not in _handlers:
        _handlers[event_key] = []
    _handlers[event_key].append(handler)


def unregister_hook(event_key: str, handler: HookHandler) -> None:
    """Remove a specific hook handler."""
    event_handlers = _handlers.get(event_key)
    if not event_handlers:
        return
    try:
        event_handlers.remove(handler)
    except ValueError:
        pass
    if not event_handlers:
        del _handlers[event_key]


def clear_hooks() -> None:
    """Clear all registered hooks (useful for testing)."""
    _handlers.clear()


def get_registered_event_keys() -> list[str]:
    """Get all registered event keys (useful for debugging)."""
    return list(_handlers.keys())


async def trigger_hook(event: HookEvent) -> None:
    """Trigger a hook event.

    Calls all handlers registered for:
    1. The general event type (e.g., 'command')
    2. The specific event:action combination (e.g., 'command:new')

    Handlers are called in registration order. Errors are caught and logged
    but don't prevent other handlers from running.
    """
    type_handlers = _handlers.get(event.type, [])
    specific_handlers = _handlers.get(f"{event.type}:{event.action}", [])
    all_handlers = type_handlers + specific_handlers

    if not all_handlers:
        return

    for handler in all_handlers:
        try:
            result = handler(event)
            if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                await result
        except Exception as exc:
            log.error(
                "Hook error [%s:%s]: %s",
                event.type, event.action, exc,
            )


def create_hook_event(
    type: HookEventType,
    action: str,
    session_key: str,
    context: dict[str, Any] | None = None,
) -> HookEvent:
    """Create a hook event with common fields filled in."""
    return HookEvent(
        type=type,
        action=action,
        session_key=session_key,
        context=context or {},
    )


# ── Type guard helpers ────────────────────────────────────────────────────

def is_agent_bootstrap_event(event: HookEvent) -> bool:
    if event.type != "agent" or event.action != "bootstrap":
        return False
    ctx = event.context
    return isinstance(ctx.get("workspaceDir"), str) and isinstance(ctx.get("bootstrapFiles"), list)


def is_gateway_startup_event(event: HookEvent) -> bool:
    return event.type == "gateway" and event.action == "startup"


def is_message_received_event(event: HookEvent) -> bool:
    if event.type != "message" or event.action != "received":
        return False
    ctx = event.context
    return isinstance(ctx.get("from"), str) and isinstance(ctx.get("channelId"), str)


def is_message_sent_event(event: HookEvent) -> bool:
    if event.type != "message" or event.action != "sent":
        return False
    ctx = event.context
    return (
        isinstance(ctx.get("to"), str)
        and isinstance(ctx.get("channelId"), str)
        and isinstance(ctx.get("success"), bool)
    )


def is_message_transcribed_event(event: HookEvent) -> bool:
    if event.type != "message" or event.action != "transcribed":
        return False
    ctx = event.context
    return isinstance(ctx.get("transcript"), str) and isinstance(ctx.get("channelId"), str)


def is_message_preprocessed_event(event: HookEvent) -> bool:
    if event.type != "message" or event.action != "preprocessed":
        return False
    ctx = event.context
    return isinstance(ctx.get("channelId"), str)
