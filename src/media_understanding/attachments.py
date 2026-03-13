"""Media understanding attachments — ported from bk/src/media-understanding/attachments*.ts.

Attachment normalization, selection, and caching.
"""
from __future__ import annotations

import os
from typing import Any

from .types import MediaAttachment, MediaUnderstandingCapability


def normalize_attachments(ctx: Any) -> list[MediaAttachment]:
    attachments: list[MediaAttachment] = []
    raw = getattr(ctx, "attachments", None) or []
    for i, att in enumerate(raw):
        path = att.get("path") if isinstance(att, dict) else getattr(att, "path", None)
        url = att.get("url") if isinstance(att, dict) else getattr(att, "url", None)
        mime = att.get("mime") if isinstance(att, dict) else getattr(att, "mime", None)
        attachments.append(MediaAttachment(path=path, url=url, mime=mime, index=i))
    return attachments


def select_attachments(
    capability: MediaUnderstandingCapability,
    attachments: list[MediaAttachment],
    policy: Any = None,
) -> list[MediaAttachment]:
    mime_prefix = {"audio": "audio/", "video": "video/", "image": "image/"}.get(capability, "")
    selected: list[MediaAttachment] = []
    for att in attachments:
        if att.already_transcribed:
            continue
        if att.mime and mime_prefix and att.mime.startswith(mime_prefix):
            selected.append(att)
            continue
        if att.path:
            ext = os.path.splitext(att.path)[1].lower()
            if capability == "audio" and ext in (".mp3", ".wav", ".ogg", ".m4a", ".flac", ".opus", ".aac"):
                selected.append(att)
            elif capability == "video" and ext in (".mp4", ".mov", ".avi", ".webm", ".mkv"):
                selected.append(att)
            elif capability == "image" and ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic"):
                selected.append(att)
    return selected


class MediaAttachmentCache:
    def __init__(self, attachments: list[MediaAttachment], max_cache_bytes: int = 50 * 1024 * 1024):
        self._attachments = attachments
        self._cache: dict[int, bytes] = {}
        self._max = max_cache_bytes

    async def get_buffer(self, index: int) -> bytes | None:
        if index in self._cache:
            return self._cache[index]
        if index >= len(self._attachments):
            return None
        att = self._attachments[index]
        if att.path and os.path.isfile(att.path):
            with open(att.path, "rb") as f:
                data = f.read()
            self._cache[index] = data
            return data
        return None

    def clear(self) -> None:
        self._cache.clear()
