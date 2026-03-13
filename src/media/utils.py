"""Media utilities — ported from remaining bk/src/media/*.ts files.

Consolidates: audio, audio-tags, base64, fetch, ffmpeg, host, image-ops,
inbound-path-policy, input-files, load-options, local-roots, outbound-attachment,
pdf-extract, png-encode, read-response-with-limit, server, sniff-mime, temp-files.
"""
from __future__ import annotations

import base64
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# ─── Audio tags ───
def parse_audio_tag(text: str) -> dict[str, Any]:
    pattern = re.compile(r"\[\[audio_as_voice\]\]", re.IGNORECASE)
    had_tag = bool(pattern.search(text))
    cleaned = pattern.sub("", text).strip() if had_tag else text
    return {"text": cleaned, "had_tag": had_tag, "audio_as_voice": had_tag}


# ─── Audio ───
async def convert_audio_to_wav(input_path: str, output_path: str | None = None) -> str:
    """Convert audio to WAV via ffmpeg (placeholder)."""
    return output_path or input_path


async def get_audio_duration_ms(path: str) -> int | None:
    """Get audio duration in milliseconds (placeholder)."""
    return None


# ─── Base64 ───
def encode_base64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def decode_base64(text: str) -> bytes:
    return base64.b64decode(text)


def sniff_mime_from_base64(data: str) -> str | None:
    try:
        raw = base64.b64decode(data[:64])
        if raw[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if raw[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
            return "image/webp"
        if raw[:6] in (b"GIF87a", b"GIF89a"):
            return "image/gif"
        if raw[:4] == b"%PDF":
            return "application/pdf"
    except Exception:
        pass
    return None


# ─── Fetch ───
async def fetch_media(url: str, headers: dict[str, str] | None = None, max_bytes: int = 5 * 1024 * 1024) -> bytes:
    """Fetch media from URL (placeholder)."""
    return b""


# ─── FFmpeg ───
FFMPEG_DEFAULT_TIMEOUT_MS = 30_000
FFMPEG_MAX_AUDIO_DURATION_SECONDS = 600
FFMPEG_MAX_VIDEO_DURATION_SECONDS = 120


async def run_ffmpeg(args: list[str], timeout_ms: int = FFMPEG_DEFAULT_TIMEOUT_MS) -> str:
    """Run ffmpeg command (placeholder)."""
    return ""


def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


# ─── Host ───
def resolve_media_host_url(host: str | None = None) -> str:
    return host or "http://127.0.0.1:9800"


# ─── Image ops ───
async def resize_image(data: bytes, max_width: int = 1280, max_height: int = 1280, fmt: str = "png") -> bytes:
    """Resize image (placeholder)."""
    return data


async def convert_heic_to_jpeg(data: bytes) -> bytes:
    """Convert HEIC to JPEG (placeholder)."""
    return data


# ─── Inbound path policy ───
def merge_inbound_path_roots(defaults: list[str], overrides: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for r in defaults + overrides:
        norm = os.path.abspath(r)
        if norm not in seen:
            seen.add(norm)
            result.append(norm)
    return result


def resolve_imessage_attachment_roots(cfg: Any = None, account_id: str = "") -> list[str]:
    return []


def is_path_within_roots(path: str, roots: list[str]) -> bool:
    abs_path = os.path.abspath(path)
    return any(abs_path.startswith(os.path.abspath(r)) for r in roots)


# ─── Input files ───
def resolve_input_files(paths: list[str], roots: list[str] | None = None) -> list[str]:
    return [p for p in paths if os.path.isfile(p)]


# ─── Load options ───
@dataclass
class MediaLoadOptions:
    max_bytes: int = 5 * 1024 * 1024
    allowed_roots: list[str] | None = None
    timeout_ms: int = 30_000


# ─── Local roots ───
def get_default_media_local_roots() -> list[str]:
    home = str(Path.home())
    return [
        os.path.join(home, "Downloads"),
        os.path.join(home, "Documents"),
        os.path.join(home, "Desktop"),
        os.path.join(home, "Pictures"),
    ]


# ─── Outbound attachment ───
@dataclass
class OutboundAttachment:
    path: str = ""
    content_type: str | None = None
    filename: str | None = None
    url: str | None = None


async def prepare_outbound_attachment(source: str, content_type: str | None = None) -> OutboundAttachment:
    return OutboundAttachment(path=source, content_type=content_type)


# ─── PDF extract ───
async def extract_pdf_text(path: str, max_pages: int = 50) -> str:
    """Extract text from PDF (placeholder)."""
    return ""


# ─── PNG encode ───
def encode_raw_to_png(data: bytes, width: int, height: int) -> bytes:
    """Encode raw RGBA to PNG (placeholder)."""
    return data


# ─── Read response with limit ───
async def read_response_with_limit(response: Any, max_bytes: int = 5 * 1024 * 1024) -> bytes:
    """Read HTTP response body with byte limit (placeholder)."""
    return b""


# ─── Server ───
async def start_media_server(port: int = 0) -> Any:
    """Start media HTTP server (placeholder)."""
    return None


# ─── Temp files ───
def create_temp_media_file(ext: str = "", prefix: str = "media-") -> str:
    fd, path = tempfile.mkstemp(suffix=ext, prefix=prefix)
    os.close(fd)
    return path


def cleanup_temp_file(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass
