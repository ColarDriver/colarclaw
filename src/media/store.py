"""Media store — ported from bk/src/media/store.ts.

Media storage: download, save from URL/local/buffer, TTL cleanup, filename sanitization.
"""
from __future__ import annotations

import os
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .mime import detect_mime, extension_for_mime

MEDIA_MAX_BYTES = 5 * 1024 * 1024  # 5MB default
DEFAULT_TTL_MS = 2 * 60 * 1000     # 2 minutes
MEDIA_FILE_MODE = 0o644


def _resolve_media_dir() -> str:
    config_dir = os.environ.get("OPENCLAW_CONFIG_DIR", str(Path.home() / ".config" / "openclaw"))
    return os.path.join(config_dir, "media")


def _sanitize_filename(name: str) -> str:
    trimmed = name.strip()
    if not trimmed:
        return ""
    sanitized = re.sub(r"[^\w._-]+", "_", trimmed, flags=re.UNICODE)
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return sanitized[:60]


def extract_original_filename(file_path: str) -> str:
    basename = os.path.basename(file_path)
    if not basename:
        return "file.bin"
    name, ext = os.path.splitext(basename)
    match = re.match(r"^(.+)---[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$", name, re.IGNORECASE)
    if match and match.group(1):
        return f"{match.group(1)}{ext}"
    return basename


@dataclass
class SavedMedia:
    id: str = ""
    path: str = ""
    size: int = 0
    content_type: str | None = None


class SaveMediaSourceError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def get_media_dir() -> str:
    return _resolve_media_dir()


async def ensure_media_dir() -> str:
    media_dir = _resolve_media_dir()
    os.makedirs(media_dir, mode=0o700, exist_ok=True)
    return media_dir


async def clean_old_media(ttl_ms: int = DEFAULT_TTL_MS, recursive: bool = False, prune_empty_dirs: bool = False) -> None:
    media_dir = await ensure_media_dir()
    now = time.time() * 1000
    idle_before = now - ttl_ms
    try:
        for entry in os.scandir(media_dir):
            if entry.is_symlink():
                continue
            if entry.is_dir() and recursive:
                _clean_dir_recursive(entry.path, idle_before, prune_empty_dirs)
                continue
            if entry.is_file():
                stat = entry.stat()
                if stat.st_mtime * 1000 < idle_before:
                    try:
                        os.remove(entry.path)
                    except OSError:
                        pass
    except FileNotFoundError:
        pass


def _clean_dir_recursive(dir_path: str, idle_before: float, prune: bool) -> bool:
    try:
        entries = list(os.scandir(dir_path))
    except OSError:
        return False
    for entry in entries:
        if entry.is_symlink():
            continue
        if entry.is_dir():
            if _clean_dir_recursive(entry.path, idle_before, prune):
                try:
                    os.rmdir(entry.path)
                except OSError:
                    pass
            continue
        if entry.is_file():
            stat = entry.stat()
            if stat.st_mtime * 1000 < idle_before:
                try:
                    os.remove(entry.path)
                except OSError:
                    pass
    if not prune:
        return False
    try:
        return len(os.listdir(dir_path)) == 0
    except OSError:
        return False


def _looks_like_url(src: str) -> bool:
    return bool(re.match(r"^https?://", src, re.IGNORECASE))


async def save_media_source(source: str, headers: dict[str, str] | None = None, subdir: str = "") -> SavedMedia:
    base_dir = _resolve_media_dir()
    dir_path = os.path.join(base_dir, subdir) if subdir else base_dir
    os.makedirs(dir_path, mode=0o700, exist_ok=True)
    base_id = str(uuid.uuid4())
    if _looks_like_url(source):
        return await _download_and_save(source, dir_path, base_id, headers)
    return await _save_local_file(source, dir_path, base_id)


async def _download_and_save(url: str, dir_path: str, base_id: str, headers: dict[str, str] | None) -> SavedMedia:
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status >= 400:
                raise IOError(f"HTTP {resp.status} downloading media")
            data = await resp.read()
            if len(data) > MEDIA_MAX_BYTES:
                raise IOError("Media exceeds 5MB limit")
            header_mime = resp.headers.get("content-type")
    mime = await detect_mime(buffer=data, header_mime=header_mime, file_path=url)
    ext = extension_for_mime(mime) or os.path.splitext(url.split("?")[0])[1] or ""
    file_id = f"{base_id}{ext}" if ext else base_id
    dest = os.path.join(dir_path, file_id)
    with open(dest, "wb") as f:
        f.write(data)
    os.chmod(dest, MEDIA_FILE_MODE)
    return SavedMedia(id=file_id, path=dest, size=len(data), content_type=mime)


async def _save_local_file(source: str, dir_path: str, base_id: str) -> SavedMedia:
    if not os.path.isfile(source):
        raise SaveMediaSourceError("not-found", "Media path does not exist")
    stat = os.stat(source)
    if stat.st_size > MEDIA_MAX_BYTES:
        raise SaveMediaSourceError("too-large", "Media exceeds 5MB limit")
    with open(source, "rb") as f:
        data = f.read()
    mime = await detect_mime(buffer=data, file_path=source)
    ext = extension_for_mime(mime) or os.path.splitext(source)[1] or ""
    file_id = f"{base_id}{ext}" if ext else base_id
    dest = os.path.join(dir_path, file_id)
    with open(dest, "wb") as f:
        f.write(data)
    os.chmod(dest, MEDIA_FILE_MODE)
    return SavedMedia(id=file_id, path=dest, size=len(data), content_type=mime)


async def save_media_buffer(
    buffer: bytes, content_type: str | None = None, subdir: str = "inbound",
    max_bytes: int = MEDIA_MAX_BYTES, original_filename: str | None = None,
) -> SavedMedia:
    if len(buffer) > max_bytes:
        raise IOError(f"Media exceeds {max_bytes // (1024 * 1024)}MB limit")
    dir_path = os.path.join(_resolve_media_dir(), subdir)
    os.makedirs(dir_path, mode=0o700, exist_ok=True)
    uid = str(uuid.uuid4())
    mime = await detect_mime(buffer=buffer, header_mime=content_type)
    ext = extension_for_mime(content_type) or extension_for_mime(mime) or ""
    if original_filename:
        base = os.path.splitext(original_filename)[0]
        sanitized = _sanitize_filename(base)
        file_id = f"{sanitized}---{uid}{ext}" if sanitized else f"{uid}{ext}"
    else:
        file_id = f"{uid}{ext}" if ext else uid
    dest = os.path.join(dir_path, file_id)
    with open(dest, "wb") as f:
        f.write(buffer)
    os.chmod(dest, MEDIA_FILE_MODE)
    return SavedMedia(id=file_id, path=dest, size=len(buffer), content_type=mime)
