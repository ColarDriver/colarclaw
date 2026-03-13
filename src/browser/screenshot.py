"""Browser screenshot — ported from bk/src/browser/screenshot.ts.

Screenshot capture and processing.
"""
from __future__ import annotations

from typing import Any


async def capture_and_save_screenshot(
    ws_url: str,
    output_path: str,
    full_page: bool = False,
    fmt: str = "png",
    quality: int = 85,
) -> dict[str, Any]:
    """Capture screenshot and save to file (placeholder)."""
    return {"ok": True, "path": output_path}


def resize_screenshot_buffer(data: bytes, max_width: int = 1280) -> bytes:
    """Resize screenshot buffer (placeholder)."""
    return data
