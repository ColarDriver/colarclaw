"""Extended media processing — download, staging, audio metadata.

Ported from bk/src/media/ remaining files not covered by existing modules.

Covers async media download, file staging for upload, audio metadata
extraction via ffprobe, and media type detection helpers.
"""
from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ─── Extended media file metadata ───

@dataclass
class MediaFileExtended:
    """Extended metadata about a media file."""
    path: str = ""
    url: str = ""
    mime_type: str = ""
    size_bytes: int = 0
    filename: str = ""
    extension: str = ""
    media_type: str = ""
    width: int = 0
    height: int = 0
    duration_ms: int = 0
    hash: str = ""
    thumbnail_path: str | None = None


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".ico", ".tiff"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac", ".opus", ".wma"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".avi", ".mov", ".mkv", ".flv", ".m4v"}


def detect_media_type(path_or_url: str) -> str:
    ext = Path(path_or_url.split("?")[0]).suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    return "document"


def hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_filename(name: str, *, max_length: int = 200) -> str:
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    safe = safe.strip(". ")
    if len(safe) > max_length:
        ext = Path(safe).suffix
        safe = safe[:max_length - len(ext)] + ext
    return safe or "unnamed"


# ─── Download ───

async def download_media(url: str, dest_dir: str) -> MediaFileExtended | None:
    try:
        import aiohttp
        os.makedirs(dest_dir, exist_ok=True)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                if resp.status != 200:
                    return None
                cd = resp.headers.get("Content-Disposition", "")
                match = re.search(r'filename="?([^";\n]+)"?', cd)
                filename = match.group(1) if match else Path(url.split("?")[0]).name or "download"
                dest = os.path.join(dest_dir, safe_filename(filename))
                with open(dest, "wb") as f:
                    async for chunk in resp.content.iter_any():
                        f.write(chunk)
                p = Path(dest)
                return MediaFileExtended(
                    path=str(p), mime_type=mimetypes.guess_type(dest)[0] or "",
                    size_bytes=p.stat().st_size, filename=p.name,
                    extension=p.suffix.lower(), media_type=detect_media_type(dest),
                    hash=hash_file(dest),
                )
    except Exception as e:
        logger.error(f"Download error: {e}")
        return None


# ─── Staging ───

class MediaStager:
    def __init__(self, staging_dir: str = ""):
        self._dir = staging_dir or tempfile.mkdtemp(prefix="openclaw-media-")

    def stage(self, source_path: str) -> str:
        os.makedirs(self._dir, exist_ok=True)
        dest = os.path.join(self._dir, safe_filename(Path(source_path).name))
        shutil.copy2(source_path, dest)
        return dest

    def stage_bytes(self, data: bytes, filename: str = "file") -> str:
        os.makedirs(self._dir, exist_ok=True)
        dest = os.path.join(self._dir, safe_filename(filename))
        with open(dest, "wb") as f:
            f.write(data)
        return dest

    def cleanup(self) -> None:
        if os.path.isdir(self._dir):
            shutil.rmtree(self._dir, ignore_errors=True)


# ─── Audio metadata ───

@dataclass
class AudioMetadata:
    duration_ms: int = 0
    sample_rate: int = 0
    channels: int = 0
    codec: str = ""
    bitrate: int = 0


def extract_audio_metadata(path: str) -> AudioMetadata:
    try:
        import subprocess, json as _json
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_format", "-show_streams",
             "-print_format", "json", path],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return AudioMetadata()
        data = _json.loads(r.stdout)
        fmt = data.get("format", {})
        audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), {})
        return AudioMetadata(
            duration_ms=int(float(fmt.get("duration", 0)) * 1000),
            sample_rate=int(audio.get("sample_rate", 0)),
            channels=int(audio.get("channels", 0)),
            codec=audio.get("codec_name", ""),
            bitrate=int(fmt.get("bit_rate", 0)),
        )
    except Exception:
        return AudioMetadata()
