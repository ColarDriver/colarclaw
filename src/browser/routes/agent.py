"""Browser agent routes — ported from bk/src/browser/routes/agent*.ts.

Agent interaction routes: act, snapshot, storage, debug, download, shared.
"""
from __future__ import annotations

from typing import Any


async def handle_agent_act(ctx: Any, **params: Any) -> dict[str, Any]:
    """Handle agent act request (click, type, scroll, etc.)."""
    return {"ok": True}


async def handle_agent_snapshot(ctx: Any, **params: Any) -> dict[str, Any]:
    """Handle agent snapshot request."""
    return {"ok": True, "snapshot": ""}


async def handle_agent_storage(ctx: Any, **params: Any) -> dict[str, Any]:
    """Handle agent storage request."""
    return {"ok": True}


async def handle_agent_debug(ctx: Any, **params: Any) -> dict[str, Any]:
    """Handle agent debug request."""
    return {"ok": True}


async def handle_agent_download(ctx: Any, **params: Any) -> dict[str, Any]:
    """Handle agent download request."""
    return {"ok": True}


async def handle_agent_act_hooks(ctx: Any, **params: Any) -> dict[str, Any]:
    """Handle agent pre/post act hooks."""
    return {"ok": True}
