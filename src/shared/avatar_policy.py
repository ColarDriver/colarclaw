"""Shared avatar policy — ported from bk/src/shared/avatar-policy.ts.

Avatar file handling: MIME detection, URL scheme classification, size limits.
"""
from __future__ import annotations

import os
import re

AVATAR_MAX_BYTES = 2 * 1024 * 1024

LOCAL_AVATAR_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}

AVATAR_MIME_BY_EXT: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}

AVATAR_DATA_RE = re.compile(r"^data:", re.IGNORECASE)
AVATAR_IMAGE_DATA_RE = re.compile(r"^data:image/", re.IGNORECASE)
AVATAR_HTTP_RE = re.compile(r"^https?://", re.IGNORECASE)
AVATAR_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.\-]*:", re.IGNORECASE)
AVATAR_PATH_EXT_RE = re.compile(r"\.(png|jpe?g|gif|webp|svg|ico)$", re.IGNORECASE)
WINDOWS_ABS_RE = re.compile(r"^[a-zA-Z]:[/\\]")


def resolve_avatar_mime(file_path: str) -> str:
    _, ext = os.path.splitext(file_path)
    return AVATAR_MIME_BY_EXT.get(ext.lower(), "application/octet-stream")


def is_avatar_data_url(value: str) -> bool:
    return bool(AVATAR_DATA_RE.match(value))


def is_avatar_image_data_url(value: str) -> bool:
    return bool(AVATAR_IMAGE_DATA_RE.match(value))


def is_avatar_http_url(value: str) -> bool:
    return bool(AVATAR_HTTP_RE.match(value))


def has_avatar_uri_scheme(value: str) -> bool:
    return bool(AVATAR_SCHEME_RE.match(value))


def is_windows_absolute_path(value: str) -> bool:
    return bool(WINDOWS_ABS_RE.match(value))


def is_local_avatar_extension(file_path: str) -> bool:
    _, ext = os.path.splitext(file_path)
    return ext.lower() in LOCAL_AVATAR_EXTENSIONS
