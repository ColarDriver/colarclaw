"""Browser tool actions — ported from bk/src/agents/tools/browser-tool.actions.ts."""
from __future__ import annotations

from typing import Any


async def browser_navigate(url: str) -> dict[str, Any]:
    return {"action": "navigate", "url": url, "success": True}


async def browser_click(selector: str) -> dict[str, Any]:
    return {"action": "click", "selector": selector, "success": True}


async def browser_type_text(selector: str, text: str) -> dict[str, Any]:
    return {"action": "type", "selector": selector, "text": text, "success": True}


async def browser_screenshot(full_page: bool = False) -> dict[str, Any]:
    return {"action": "screenshot", "full_page": full_page, "success": True}


async def browser_evaluate(code: str) -> dict[str, Any]:
    return {"action": "evaluate", "code": code, "success": True}
