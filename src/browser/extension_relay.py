"""Browser extension relay — ported from bk/src/browser/extension-relay.ts + extension-relay-auth.ts.

Chrome extension relay: message routing, authentication, CDP bridging.
"""
from __future__ import annotations

from typing import Any


async def start_extension_relay(port: int, auth: Any = None) -> Any:
    """Start extension relay (placeholder)."""
    return None


async def stop_extension_relay(relay: Any = None) -> None:
    """Stop extension relay (placeholder)."""
    pass


def resolve_extension_relay_auth(cfg: Any = None) -> dict[str, Any]:
    """Resolve extension relay auth config."""
    return {}
