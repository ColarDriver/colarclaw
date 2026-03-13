"""Browser tab routes — ported from bk/src/browser/routes/tabs.ts.

Tab management: list, open, close, focus, action.
"""
from __future__ import annotations

from typing import Any


async def handle_list_tabs(ctx: Any, profile: str | None = None) -> dict[str, Any]:
    return {"running": False, "tabs": []}


async def handle_open_tab(ctx: Any, url: str = "", profile: str | None = None) -> dict[str, Any]:
    return {"targetId": "", "title": "", "url": url}


async def handle_close_tab(ctx: Any, target_id: str = "", profile: str | None = None) -> dict[str, Any]:
    return {"ok": True}


async def handle_focus_tab(ctx: Any, target_id: str = "", profile: str | None = None) -> dict[str, Any]:
    return {"ok": True}


async def handle_tab_action(ctx: Any, action: str = "list", index: int | None = None, profile: str | None = None) -> dict[str, Any]:
    return {"ok": True}
