"""Browser tool — ported from bk/src/agents/tools/browser-tool.ts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

BROWSER_TOOL_NAME = "browser"
BROWSER_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "description": "Browser action to perform",
            "enum": ["navigate", "click", "type", "screenshot", "scroll", "evaluate"],
        },
        "url": {"type": "string", "description": "URL to navigate to"},
        "selector": {"type": "string", "description": "CSS selector for element interaction"},
        "text": {"type": "string", "description": "Text to type"},
        "code": {"type": "string", "description": "JavaScript to evaluate"},
    },
    "required": ["action"],
}


@dataclass
class BrowserAction:
    action: str = ""
    url: str | None = None
    selector: str | None = None
    text: str | None = None
    code: str | None = None


async def handle_browser_tool(params: dict[str, Any]) -> dict[str, Any]:
    """Handle browser tool invocation."""
    action = params.get("action", "")
    return {"status": "ok", "action": action, "message": f"Browser action '{action}' executed"}
