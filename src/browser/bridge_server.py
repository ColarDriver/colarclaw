"""Browser bridge server — ported from bk/src/browser/bridge-server.ts.

WebSocket bridge server for browser extension communication.
"""
from __future__ import annotations

from typing import Any


async def start_bridge_server(port: int, auth_token: str | None = None) -> Any:
    """Start the bridge WebSocket server (placeholder)."""
    return None


async def stop_bridge_server(server: Any = None) -> None:
    """Stop the bridge server (placeholder)."""
    pass
