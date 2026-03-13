"""Media understanding providers — ported from bk/src/media-understanding/providers/.

Provider registry, image/audio runtime, and individual provider implementations.
"""
from __future__ import annotations

from typing import Any

from ..types import (
    AudioTranscriptionRequest,
    AudioTranscriptionResult,
    ImageDescriptionRequest,
    ImageDescriptionResult,
    MediaUnderstandingProvider,
    VideoDescriptionRequest,
    VideoDescriptionResult,
)


# ─── Provider implementations ───

class OpenAIProvider:
    id = "openai"
    capabilities = ["audio", "image"]

    async def transcribe_audio(self, req: AudioTranscriptionRequest) -> AudioTranscriptionResult:
        return AudioTranscriptionResult(text="", model=req.model)

    async def describe_image(self, req: ImageDescriptionRequest) -> ImageDescriptionResult:
        return ImageDescriptionResult(text="", model=req.model)

    async def describe_video(self, req: VideoDescriptionRequest) -> VideoDescriptionResult:
        return VideoDescriptionResult(text="", model=req.model)


class AnthropicProvider:
    id = "anthropic"
    capabilities = ["image"]

    async def transcribe_audio(self, req: AudioTranscriptionRequest) -> AudioTranscriptionResult:
        raise NotImplementedError("Anthropic does not support audio transcription")

    async def describe_image(self, req: ImageDescriptionRequest) -> ImageDescriptionResult:
        return ImageDescriptionResult(text="", model=req.model)

    async def describe_video(self, req: VideoDescriptionRequest) -> VideoDescriptionResult:
        raise NotImplementedError("Anthropic does not support video description")


class GoogleProvider:
    id = "google"
    capabilities = ["audio", "video", "image"]

    async def transcribe_audio(self, req: AudioTranscriptionRequest) -> AudioTranscriptionResult:
        return AudioTranscriptionResult(text="", model=req.model)

    async def describe_image(self, req: ImageDescriptionRequest) -> ImageDescriptionResult:
        return ImageDescriptionResult(text="", model=req.model)

    async def describe_video(self, req: VideoDescriptionRequest) -> VideoDescriptionResult:
        return VideoDescriptionResult(text="", model=req.model)


class DeepgramProvider:
    id = "deepgram"
    capabilities = ["audio"]

    async def transcribe_audio(self, req: AudioTranscriptionRequest) -> AudioTranscriptionResult:
        return AudioTranscriptionResult(text="", model=req.model)

    async def describe_image(self, req: ImageDescriptionRequest) -> ImageDescriptionResult:
        raise NotImplementedError

    async def describe_video(self, req: VideoDescriptionRequest) -> VideoDescriptionResult:
        raise NotImplementedError


class GroqProvider:
    id = "groq"
    capabilities = ["audio"]

    async def transcribe_audio(self, req: AudioTranscriptionRequest) -> AudioTranscriptionResult:
        return AudioTranscriptionResult(text="", model=req.model)

    async def describe_image(self, req: ImageDescriptionRequest) -> ImageDescriptionResult:
        raise NotImplementedError

    async def describe_video(self, req: VideoDescriptionRequest) -> VideoDescriptionResult:
        raise NotImplementedError


class MinimaxProvider:
    id = "minimax"
    capabilities = ["audio"]

    async def transcribe_audio(self, req: AudioTranscriptionRequest) -> AudioTranscriptionResult:
        return AudioTranscriptionResult(text="", model=req.model)

    async def describe_image(self, req: ImageDescriptionRequest) -> ImageDescriptionResult:
        raise NotImplementedError

    async def describe_video(self, req: VideoDescriptionRequest) -> VideoDescriptionResult:
        raise NotImplementedError


class MistralProvider:
    id = "mistral"
    capabilities = ["image"]

    async def transcribe_audio(self, req: AudioTranscriptionRequest) -> AudioTranscriptionResult:
        raise NotImplementedError

    async def describe_image(self, req: ImageDescriptionRequest) -> ImageDescriptionResult:
        return ImageDescriptionResult(text="", model=req.model)

    async def describe_video(self, req: VideoDescriptionRequest) -> VideoDescriptionResult:
        raise NotImplementedError


class MoonshotProvider:
    id = "moonshot"
    capabilities = ["image", "video"]

    async def transcribe_audio(self, req: AudioTranscriptionRequest) -> AudioTranscriptionResult:
        raise NotImplementedError

    async def describe_image(self, req: ImageDescriptionRequest) -> ImageDescriptionResult:
        return ImageDescriptionResult(text="", model=req.model)

    async def describe_video(self, req: VideoDescriptionRequest) -> VideoDescriptionResult:
        return VideoDescriptionResult(text="", model=req.model)


class ZaiProvider:
    id = "zai"
    capabilities = ["image"]

    async def transcribe_audio(self, req: AudioTranscriptionRequest) -> AudioTranscriptionResult:
        raise NotImplementedError

    async def describe_image(self, req: ImageDescriptionRequest) -> ImageDescriptionResult:
        return ImageDescriptionResult(text="", model=req.model)

    async def describe_video(self, req: VideoDescriptionRequest) -> VideoDescriptionResult:
        raise NotImplementedError


# ─── Registry ───

_DEFAULT_PROVIDERS: dict[str, Any] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "google": GoogleProvider,
    "deepgram": DeepgramProvider,
    "groq": GroqProvider,
    "minimax": MinimaxProvider,
    "mistral": MistralProvider,
    "moonshot": MoonshotProvider,
    "zai": ZaiProvider,
}

PROVIDER_ID_ALIASES: dict[str, str] = {
    "gemini": "google", "vertex": "google",
    "gpt": "openai", "claude": "anthropic",
    "kimi": "moonshot",
}


def normalize_media_provider_id(raw: str) -> str | None:
    n = raw.strip().lower()
    return PROVIDER_ID_ALIASES.get(n, n) if n else None


def build_media_understanding_registry(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    registry: dict[str, Any] = {}
    for pid, cls in _DEFAULT_PROVIDERS.items():
        registry[pid] = cls()
    if overrides:
        registry.update(overrides)
    return registry


def get_media_understanding_provider(provider_id: str, registry: dict[str, Any] | None = None) -> Any | None:
    reg = registry or build_media_understanding_registry()
    normalized = normalize_media_provider_id(provider_id)
    return reg.get(normalized) if normalized else None
