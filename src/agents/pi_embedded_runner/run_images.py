"""Pi embedded runner run images — ported from bk/src/agents/pi-embedded-runner/run/images.ts."""
from __future__ import annotations

import base64
import os
from typing import Any


def encode_image_to_base64(file_path: str) -> str | None:
    try:
        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        return None


def build_image_content_block(
    image_data: str,
    media_type: str = "image/png",
) -> dict[str, Any]:
    return {
        "type": "image_url",
        "image_url": {
            "url": f"data:{media_type};base64,{image_data}",
        },
    }


def resolve_media_type(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
    }.get(ext, "image/png")
