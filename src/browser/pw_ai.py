"""Browser Playwright AI — ported from bk/src/browser/pw-ai.ts + pw-ai-module.ts + pw-ai-state.ts + pw-role-snapshot.ts.

AI-powered browser interaction: snapshot-for-AI, role snapshots, AI module loader.
"""
from __future__ import annotations

from typing import Any

_pw_ai_loaded = False


def is_pw_ai_loaded() -> bool:
    return _pw_ai_loaded


def mark_pw_ai_loaded() -> None:
    global _pw_ai_loaded
    _pw_ai_loaded = True


async def snapshot_for_ai(page: Any, timeout: int = 5000, track: str | None = None) -> dict[str, str]:
    """Get AI-friendly snapshot (placeholder)."""
    return {"full": "", "incremental": None}


async def close_playwright_browser_connection() -> None:
    """Close Playwright connection (placeholder)."""
    pass


def build_role_snapshot(snapshot_text: str, max_chars: int = 80000, efficient: bool = False, depth: int | None = None) -> dict[str, Any]:
    """Build role-based snapshot from text (placeholder)."""
    return {"snapshot": "", "refs": {}, "stats": {}}
