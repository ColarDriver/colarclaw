"""Media tool shared — ported from bk/src/agents/tools/media-tool-shared.ts."""
from __future__ import annotations

import os
from typing import Any

SUPPORTED_MEDIA_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".mp4", ".webm", ".mp3", ".wav", ".pdf"}


def is_supported_media(file_path: str) -> bool:
    return os.path.splitext(file_path)[1].lower() in SUPPORTED_MEDIA_EXTENSIONS


def resolve_media_mime_type(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    return {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
        ".mp4": "video/mp4", ".webm": "video/webm",
        ".mp3": "audio/mpeg", ".wav": "audio/wav",
        ".pdf": "application/pdf",
    }.get(ext, "application/octet-stream")
