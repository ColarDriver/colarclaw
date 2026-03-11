"""Image tool helpers — ported from bk/src/agents/tools/image-tool.helpers.ts."""
from __future__ import annotations

import os
from typing import Any


def detect_image_format(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    return {"png": "png", "jpg": "jpeg", "jpeg": "jpeg",
            "gif": "gif", "webp": "webp"}.get(ext.lstrip("."), "png")


def validate_image_path(file_path: str) -> bool:
    if not os.path.isfile(file_path):
        return False
    ext = os.path.splitext(file_path)[1].lower()
    return ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")


def build_image_output_path(output_dir: str, name: str, fmt: str = "png") -> str:
    os.makedirs(output_dir, exist_ok=True)
    return os.path.join(output_dir, f"{name}.{fmt}")
