"""Media understanding utilities — ported from remaining bk/src/media-understanding/*.ts.

Consolidates: apply, audio-preflight, audio-transcription-runner, concurrency,
defaults, echo-transcript, errors, format, fs, output-extract, resolve, scope,
transcribe-audio, video.
"""
from __future__ import annotations

import asyncio
import os
import re
from typing import Any, Literal

from .types import MediaAttachment, MediaUnderstandingCapability

# ─── Defaults ───
AUTO_AUDIO_KEY_PROVIDERS = ["openai", "deepgram", "groq", "google", "minimax"]
AUTO_IMAGE_KEY_PROVIDERS = ["openai", "anthropic", "google", "mistral", "moonshot", "zai"]
AUTO_VIDEO_KEY_PROVIDERS = ["google", "moonshot"]

DEFAULT_IMAGE_MODELS: dict[str, str] = {
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-4-20250514",
    "google": "gemini-2.0-flash",
    "mistral": "pixtral-large-latest",
    "moonshot": "moonshot-v1-vision",
    "zai": "zai-vision",
}


# ─── Errors ───
class MediaUnderstandingSkipError(Exception):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


def is_media_understanding_skip_error(err: Exception) -> bool:
    return isinstance(err, MediaUnderstandingSkipError)


# ─── Scope ───
def resolve_scope_decision(scope: Any = None, ctx: Any = None) -> Literal["allow", "deny"]:
    if not scope:
        return "allow"
    enabled = scope.get("enabled") if isinstance(scope, dict) else getattr(scope, "enabled", None)
    if enabled is False:
        return "deny"
    return "allow"


# ─── Resolve ───
def resolve_model_entries(cfg: Any = None, capability: str = "", config: Any = None, provider_registry: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if not config:
        return []
    models = config.get("models") if isinstance(config, dict) else getattr(config, "models", None)
    if not models or not isinstance(models, list):
        return []
    return [m for m in models if isinstance(m, dict)]


# ─── Concurrency ───
class ConcurrencyLimiter:
    def __init__(self, max_concurrent: int = 3):
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def run(self, coro: Any) -> Any:
        async with self._semaphore:
            return await coro


# ─── Format ───
def format_transcription_text(text: str, kind: str = "audio") -> str:
    trimmed = text.strip()
    if not trimmed:
        return ""
    return f"[{kind} transcription] {trimmed}"


def format_description_text(text: str, kind: str = "image") -> str:
    trimmed = text.strip()
    if not trimmed:
        return ""
    return f"[{kind} description] {trimmed}"


# ─── Apply ───
def apply_media_understanding_outputs(body: str, outputs: list[dict[str, Any]]) -> str:
    if not outputs:
        return body
    parts = [body.rstrip()] if body.strip() else []
    for out in outputs:
        text = out.get("text", "").strip()
        if text:
            parts.append(text)
    return "\n\n".join(parts)


# ─── Audio preflight ───
async def audio_preflight_check(path: str) -> dict[str, Any]:
    if not os.path.isfile(path):
        return {"ok": False, "reason": "file not found"}
    stat = os.stat(path)
    if stat.st_size == 0:
        return {"ok": False, "reason": "empty file"}
    if stat.st_size > 100 * 1024 * 1024:
        return {"ok": False, "reason": "file too large"}
    return {"ok": True}


# ─── Echo transcript ───
def extract_echo_transcript(text: str) -> str | None:
    match = re.search(r"\[transcript\](.*?)\[/transcript\]", text, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else None


# ─── FS ───
async def file_exists(path: str) -> bool:
    return os.path.isfile(path)


# ─── Output extract ───
def extract_gemini_response(stdout: str) -> str | None:
    try:
        import json
        data = json.loads(stdout)
        if isinstance(data, dict):
            return data.get("text") or data.get("response") or data.get("output")
    except Exception:
        pass
    return None


# ─── Transcribe audio ───
async def transcribe_audio_file(path: str, provider: str = "openai", **kwargs: Any) -> dict[str, Any]:
    """Transcribe audio file (placeholder)."""
    return {"text": "", "provider": provider}


# ─── Video ───
async def describe_video_file(path: str, provider: str = "google", **kwargs: Any) -> dict[str, Any]:
    """Describe video file (placeholder)."""
    return {"text": "", "provider": provider}
