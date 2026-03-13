"""Browser client actions — ported from bk/src/browser/client-actions*.ts.

Client-side browser actions: core, observe, state, types, URL.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass
class BrowserActionResult:
    ok: bool = True
    error: str | None = None
    data: Any = None


ActionType = Literal["click", "type", "scroll", "hover", "select", "navigate", "wait", "evaluate", "screenshot", "upload"]


async def execute_browser_action(
    base_url: str | None,
    action: ActionType,
    target_id: str | None = None,
    ref: str | None = None,
    profile: str | None = None,
    **params: Any,
) -> BrowserActionResult:
    """Execute a browser action (placeholder)."""
    return BrowserActionResult()


async def observe_page(base_url: str | None = None, target_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
    """Observe page state: console, errors, network (placeholder)."""
    return {"console": [], "errors": [], "requests": []}


async def get_page_state(base_url: str | None = None, target_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
    """Get page state summary (placeholder)."""
    return {}


async def navigate_to_url(base_url: str | None = None, url: str = "", target_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
    """Navigate to URL (placeholder)."""
    return {"ok": True}
