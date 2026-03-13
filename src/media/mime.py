"""Media MIME — ported from bk/src/media/mime.ts.

MIME detection, extension mapping, file type sniffing.
"""
from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlparse

from .constants import MediaKind, media_kind_from_mime

EXT_BY_MIME: dict[str, str] = {
    "image/heic": ".heic", "image/heif": ".heif", "image/jpeg": ".jpg",
    "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif",
    "audio/ogg": ".ogg", "audio/mpeg": ".mp3", "audio/x-m4a": ".m4a",
    "audio/mp4": ".m4a", "video/mp4": ".mp4", "video/quicktime": ".mov",
    "application/pdf": ".pdf", "application/json": ".json",
    "application/zip": ".zip", "application/gzip": ".gz",
    "application/x-tar": ".tar", "application/x-7z-compressed": ".7z",
    "application/vnd.rar": ".rar", "application/msword": ".doc",
    "application/vnd.ms-excel": ".xls", "application/vnd.ms-powerpoint": ".ppt",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "text/csv": ".csv", "text/plain": ".txt", "text/markdown": ".md",
}

MIME_BY_EXT: dict[str, str] = {v: k for k, v in EXT_BY_MIME.items()}
MIME_BY_EXT[".jpeg"] = "image/jpeg"
MIME_BY_EXT[".js"] = "text/javascript"

AUDIO_FILE_EXTENSIONS = frozenset([".aac", ".caf", ".flac", ".m4a", ".mp3", ".oga", ".ogg", ".opus", ".wav"])


def normalize_mime_type(mime: str | None) -> str | None:
    if not mime:
        return None
    cleaned = mime.split(";")[0].strip().lower()
    return cleaned or None


def get_file_extension(file_path: str | None) -> str | None:
    if not file_path:
        return None
    try:
        if re.match(r"^https?://", file_path, re.IGNORECASE):
            parsed = urlparse(file_path)
            ext = os.path.splitext(parsed.path)[1].lower()
            return ext or None
    except Exception:
        pass
    ext = os.path.splitext(file_path)[1].lower()
    return ext or None


def is_audio_file_name(file_name: str | None) -> bool:
    ext = get_file_extension(file_name)
    return ext in AUDIO_FILE_EXTENSIONS if ext else False


def _is_generic_mime(mime: str | None) -> bool:
    if not mime:
        return True
    return mime.lower() in ("application/octet-stream", "application/zip")


async def detect_mime(buffer: bytes | None = None, header_mime: str | None = None, file_path: str | None = None) -> str | None:
    ext = get_file_extension(file_path)
    ext_mime = MIME_BY_EXT.get(ext) if ext else None
    normalized_header = normalize_mime_type(header_mime)
    sniffed: str | None = None
    if buffer:
        try:
            import magic
            sniffed = magic.from_buffer(buffer, mime=True)
        except Exception:
            pass
    if sniffed and (not _is_generic_mime(sniffed) or not ext_mime):
        return sniffed
    if ext_mime:
        return ext_mime
    if normalized_header and not _is_generic_mime(normalized_header):
        return normalized_header
    if sniffed:
        return sniffed
    if normalized_header:
        return normalized_header
    return None


def extension_for_mime(mime: str | None) -> str | None:
    normalized = normalize_mime_type(mime)
    return EXT_BY_MIME.get(normalized) if normalized else None


def is_gif_media(content_type: str | None = None, file_name: str | None = None) -> bool:
    if content_type and content_type.lower() == "image/gif":
        return True
    return get_file_extension(file_name) == ".gif"


def image_mime_from_format(fmt: str | None) -> str | None:
    if not fmt:
        return None
    mapping = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "heic": "image/heic",
               "heif": "image/heif", "png": "image/png", "webp": "image/webp", "gif": "image/gif"}
    return mapping.get(fmt.lower())


def kind_from_mime(mime: str | None) -> MediaKind | None:
    return media_kind_from_mime(normalize_mime_type(mime))
