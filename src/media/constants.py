"""Media constants — ported from bk/src/media/constants.ts."""
from __future__ import annotations

from typing import Literal

MAX_IMAGE_BYTES = 6 * 1024 * 1024      # 6MB
MAX_AUDIO_BYTES = 16 * 1024 * 1024     # 16MB
MAX_VIDEO_BYTES = 16 * 1024 * 1024     # 16MB
MAX_DOCUMENT_BYTES = 100 * 1024 * 1024 # 100MB

MediaKind = Literal["image", "audio", "video", "document"]


def media_kind_from_mime(mime: str | None) -> MediaKind | None:
    if not mime:
        return None
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("audio/"):
        return "audio"
    if mime.startswith("video/"):
        return "video"
    if mime == "application/pdf":
        return "document"
    if mime.startswith("text/"):
        return "document"
    if mime.startswith("application/"):
        return "document"
    return None


def max_bytes_for_kind(kind: MediaKind) -> int:
    return {
        "image": MAX_IMAGE_BYTES,
        "audio": MAX_AUDIO_BYTES,
        "video": MAX_VIDEO_BYTES,
        "document": MAX_DOCUMENT_BYTES,
    }.get(kind, MAX_DOCUMENT_BYTES)
