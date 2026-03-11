"""Tool images — ported from bk/src/agents/tool-images.ts."""
from __future__ import annotations
import base64
import mimetypes
import os
from typing import Any

SUPPORTED_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"})

def is_image_path(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in SUPPORTED_IMAGE_EXTENSIONS

def read_image_as_base64(path: str) -> str | None:
    try:
        with open(path, "rb") as f:
            data = f.read()
        return base64.b64encode(data).decode("ascii")
    except Exception:
        return None

def build_image_data_url(path: str) -> str | None:
    mime = mimetypes.guess_type(path)[0] or "image/png"
    b64 = read_image_as_base64(path)
    if not b64:
        return None
    return f"data:{mime};base64,{b64}"

def extract_image_blocks(content: list[Any]) -> list[dict[str, Any]]:
    images = []
    for block in content:
        if isinstance(block, dict):
            btype = block.get("type")
            if btype == "image" or btype == "image_url":
                images.append(block)
    return images
