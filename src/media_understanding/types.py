"""Media understanding types — ported from bk/src/media-understanding/types.ts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Literal, Protocol

MediaUnderstandingKind = Literal["audio.transcription", "video.description", "image.description"]
MediaUnderstandingCapability = Literal["image", "audio", "video"]
MediaUnderstandingDecisionOutcome = Literal["success", "skipped", "disabled", "no-attachment", "scope-deny"]


@dataclass
class MediaAttachment:
    path: str | None = None
    url: str | None = None
    mime: str | None = None
    index: int = 0
    already_transcribed: bool = False


@dataclass
class MediaUnderstandingOutput:
    kind: MediaUnderstandingKind = "audio.transcription"
    attachment_index: int = 0
    text: str = ""
    provider: str = ""
    model: str | None = None


@dataclass
class MediaUnderstandingModelDecision:
    provider: str | None = None
    model: str | None = None
    type: str = "provider"
    outcome: str = "success"
    reason: str | None = None


@dataclass
class MediaUnderstandingAttachmentDecision:
    attachment_index: int = 0
    attempts: list[MediaUnderstandingModelDecision] = field(default_factory=list)
    chosen: MediaUnderstandingModelDecision | None = None


@dataclass
class MediaUnderstandingDecision:
    capability: MediaUnderstandingCapability = "audio"
    outcome: MediaUnderstandingDecisionOutcome = "success"
    attachments: list[MediaUnderstandingAttachmentDecision] = field(default_factory=list)


@dataclass
class AudioTranscriptionRequest:
    buffer: bytes = b""
    file_name: str = ""
    mime: str | None = None
    api_key: str = ""
    base_url: str | None = None
    headers: dict[str, str] | None = None
    model: str | None = None
    language: str | None = None
    prompt: str | None = None
    timeout_ms: int = 30000


@dataclass
class AudioTranscriptionResult:
    text: str = ""
    model: str | None = None


@dataclass
class VideoDescriptionRequest:
    buffer: bytes = b""
    file_name: str = ""
    mime: str | None = None
    api_key: str = ""
    base_url: str | None = None
    headers: dict[str, str] | None = None
    model: str | None = None
    prompt: str | None = None
    timeout_ms: int = 30000


@dataclass
class VideoDescriptionResult:
    text: str = ""
    model: str | None = None


@dataclass
class ImageDescriptionRequest:
    buffer: bytes = b""
    file_name: str = ""
    mime: str | None = None
    model: str = ""
    provider: str = ""
    prompt: str | None = None
    max_tokens: int | None = None
    timeout_ms: int = 30000
    profile: str | None = None
    agent_dir: str = ""
    cfg: Any = None


@dataclass
class ImageDescriptionResult:
    text: str = ""
    model: str | None = None


class MediaUnderstandingProvider(Protocol):
    id: str
    capabilities: list[MediaUnderstandingCapability]
    async def transcribe_audio(self, req: AudioTranscriptionRequest) -> AudioTranscriptionResult: ...
    async def describe_video(self, req: VideoDescriptionRequest) -> VideoDescriptionResult: ...
    async def describe_image(self, req: ImageDescriptionRequest) -> ImageDescriptionResult: ...
