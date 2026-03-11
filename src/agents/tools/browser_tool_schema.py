"""Browser tool schema — ported from bk/src/agents/tools/browser-tool.schema.ts."""
from __future__ import annotations

BROWSER_ACTION_SCHEMAS = {
    "navigate": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to navigate to"},
        },
        "required": ["url"],
    },
    "click": {
        "type": "object",
        "properties": {
            "selector": {"type": "string", "description": "CSS selector to click"},
        },
        "required": ["selector"],
    },
    "type": {
        "type": "object",
        "properties": {
            "selector": {"type": "string"},
            "text": {"type": "string"},
        },
        "required": ["selector", "text"],
    },
    "screenshot": {
        "type": "object",
        "properties": {
            "full_page": {"type": "boolean", "description": "Capture full page"},
        },
    },
    "scroll": {
        "type": "object",
        "properties": {
            "direction": {"type": "string", "enum": ["up", "down"]},
            "amount": {"type": "integer"},
        },
    },
    "evaluate": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "JavaScript to evaluate"},
        },
        "required": ["code"],
    },
}
