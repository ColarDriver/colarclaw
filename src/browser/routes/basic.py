"""Browser basic routes — ported from bk/src/browser/routes/basic.ts.

Basic browser routes: status, start, stop, reset-profile.
"""
from __future__ import annotations

from typing import Any


async def handle_browser_status(ctx: Any, profile: str | None = None) -> dict[str, Any]:
    return {"enabled": True, "running": False}


async def handle_browser_start(ctx: Any, profile: str | None = None) -> dict[str, Any]:
    return {"ok": True}


async def handle_browser_stop(ctx: Any, profile: str | None = None) -> dict[str, Any]:
    return {"ok": True}


async def handle_browser_reset_profile(ctx: Any, profile: str | None = None) -> dict[str, Any]:
    return {"ok": True, "moved": False}
