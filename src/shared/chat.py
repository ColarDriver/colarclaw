"""Shared chat types — ported from bk/src/shared/chat-envelope.ts,
chat-content.ts, chat-message-content.ts.

Chat envelope, content, and message content type definitions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


# ─── chat-content.ts ───

ContentPartType = Literal["text", "image", "audio", "file", "tool_call", "tool_result"]


@dataclass
class TextContentPart:
    type: str = "text"
    text: str = ""


@dataclass
class ImageContentPart:
    type: str = "image"
    url: str = ""
    mime_type: str = ""
    alt_text: str = ""


@dataclass
class AudioContentPart:
    type: str = "audio"
    url: str = ""
    mime_type: str = ""
    transcript: str = ""


@dataclass
class FileContentPart:
    type: str = "file"
    url: str = ""
    name: str = ""
    mime_type: str = ""


@dataclass
class ToolCallContentPart:
    type: str = "tool_call"
    tool_call_id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass
class ToolResultContentPart:
    type: str = "tool_result"
    tool_call_id: str = ""
    content: str = ""
    is_error: bool = False


# ─── chat-envelope.ts ───

@dataclass
class ChatEnvelope:
    role: str = ""  # "user" | "assistant" | "system" | "tool"
    content: list[Any] = field(default_factory=list)
    name: str = ""
    tool_calls: list[Any] = field(default_factory=list)
    tool_call_id: str = ""


@dataclass
class ChatMessage:
    id: str = ""
    role: str = ""
    content: str = ""
    parts: list[Any] = field(default_factory=list)
    name: str = ""
    timestamp_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


# ─── chat-message-content.ts ───

def extract_text_from_content(content: Any) -> str:
    """Extract plain text from chat content."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for part in content:
            if isinstance(part, str):
                texts.append(part)
            elif isinstance(part, dict) and part.get("type") == "text":
                texts.append(part.get("text", ""))
            elif hasattr(part, "type") and part.type == "text":
                texts.append(part.text)
        return "\n".join(texts)
    return ""


def has_non_text_content(content: Any) -> bool:
    """Check if content has non-text parts (images, audio, files)."""
    if isinstance(content, str):
        return False
    if isinstance(content, list):
        return any(
            (isinstance(p, dict) and p.get("type") not in ("text", None))
            or (hasattr(p, "type") and p.type not in ("text", None))
            for p in content
        )
    return False
