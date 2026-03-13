"""Hooks package."""
from .engine import (
    HookEvent,
    HookEventType,
    HookHandler,
    clear_hooks,
    create_hook_event,
    get_registered_event_keys,
    register_hook,
    trigger_hook,
    unregister_hook,
)
from .types import (
    Hook,
    HookEntry,
    HookInstallSpec,
    HookInvocationPolicy,
    HookSnapshot,
    OpenClawHookMetadata,
)

__all__ = [
    "HookEvent",
    "HookEventType",
    "HookHandler",
    "register_hook",
    "unregister_hook",
    "clear_hooks",
    "get_registered_event_keys",
    "trigger_hook",
    "create_hook_event",
    "Hook",
    "HookEntry",
    "HookInstallSpec",
    "HookInvocationPolicy",
    "HookSnapshot",
    "OpenClawHookMetadata",
]
