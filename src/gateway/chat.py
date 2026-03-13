"""Gateway chat — ported from bk/src/gateway/ chat files.

Chat abort, attachment handling, message sanitization, agent prompts, identity.
Consolidates: chat-abort.ts, chat-attachments.ts, chat-sanitize.ts,
  agent-event-assistant-text.ts, agent-prompt.ts, assistant-identity.ts,
  server-chat.ts (chat-specific logic).
"""
from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


# ─── chat-abort.ts — enhanced with session-level abort ───

@dataclass
class ChatAbortControllerEntry:
    """Tracks an active chat abort controller."""
    session_key: str = ""
    run_id: str = ""
    abort_reason: str | None = None
    aborted: bool = False
    created_at_ms: int = 0


class ChatAbortManager:
    """Manages abort controllers for in-flight chat requests.

    Supports both request-level and session-level abort operations.
    """

    def __init__(self) -> None:
        self._controllers: dict[str, ChatAbortControllerEntry] = {}

    def register(self, request_id: str, session_key: str = "", run_id: str = "") -> ChatAbortControllerEntry:
        entry = ChatAbortControllerEntry(
            session_key=session_key,
            run_id=run_id or request_id,
            created_at_ms=int(time.time() * 1000),
        )
        self._controllers[request_id] = entry
        return entry

    def abort(self, request_id: str, *, reason: str = "user abort") -> bool:
        entry = self._controllers.get(request_id)
        if entry and not entry.aborted:
            entry.aborted = True
            entry.abort_reason = reason
            return True
        return False

    def abort_session(self, session_key: str, *, reason: str = "user abort") -> list[ChatAbortControllerEntry]:
        """Abort all runs for a session."""
        aborted: list[ChatAbortControllerEntry] = []
        for entry in self._controllers.values():
            if entry.session_key == session_key and not entry.aborted:
                entry.aborted = True
                entry.abort_reason = reason
                aborted.append(entry)
        return aborted

    def is_aborted(self, request_id: str) -> bool:
        entry = self._controllers.get(request_id)
        return entry.aborted if entry else False

    def unregister(self, request_id: str) -> ChatAbortControllerEntry | None:
        return self._controllers.pop(request_id, None)

    def abort_all(self) -> int:
        count = 0
        for entry in self._controllers.values():
            if not entry.aborted:
                entry.aborted = True
                entry.abort_reason = "abort_all"
                count += 1
        return count

    def clear(self) -> None:
        self._controllers.clear()


# ─── chat-attachments.ts ───

SUPPORTED_ATTACHMENT_MIMES = frozenset({
    "image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml",
    "audio/wav", "audio/mp3", "audio/mpeg", "audio/ogg", "audio/webm",
    "video/mp4", "video/webm",
    "application/pdf",
    "text/plain", "text/markdown", "text/csv",
    "application/json", "application/xml",
})

MAX_ATTACHMENT_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB
MAX_ATTACHMENTS_PER_MESSAGE = 10


@dataclass
class ChatAttachment:
    id: str = ""
    name: str = ""
    mime_type: str = ""
    size_bytes: int = 0
    url: str = ""
    data_uri: str = ""
    data: bytes | None = None
    type: str = ""  # "image" | "audio" | "video" | "file"


def validate_chat_attachment(attachment: ChatAttachment) -> str | None:
    """Validate a chat attachment. Returns error message or None."""
    if not attachment.name and not attachment.url and not attachment.data_uri:
        return "attachment missing name, url, or data"
    if attachment.size_bytes > MAX_ATTACHMENT_SIZE_BYTES:
        return f"attachment too large: {attachment.size_bytes} > {MAX_ATTACHMENT_SIZE_BYTES}"
    if attachment.mime_type and attachment.mime_type not in SUPPORTED_ATTACHMENT_MIMES:
        return f"unsupported MIME type: {attachment.mime_type}"
    return None


def normalize_attachment(raw: dict[str, Any]) -> ChatAttachment:
    """Normalize a raw attachment dict into a ChatAttachment."""
    mime = raw.get("mimeType", raw.get("mime_type", ""))
    return ChatAttachment(
        id=raw.get("id", str(uuid.uuid4())),
        name=raw.get("name", ""),
        mime_type=mime,
        size_bytes=int(raw.get("sizeBytes", raw.get("size_bytes", 0))),
        url=raw.get("url", ""),
        data_uri=raw.get("dataUri", raw.get("data_uri", "")),
        type=_infer_attachment_type(mime),
    )


def _infer_attachment_type(mime_type: str) -> str:
    """Infer attachment type from MIME type."""
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("audio/"):
        return "audio"
    if mime_type.startswith("video/"):
        return "video"
    return "file"


# ─── chat-sanitize.ts ───

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_EXCESS_NEWLINE_RE = re.compile(r"\n{4,}")
_EXCESS_SPACE_RE = re.compile(r" {20,}")
_SCRIPT_RE = re.compile(r'<script\b[^>]*>.*?</script>', re.I | re.S)
_IFRAME_RE = re.compile(r'<iframe\b[^>]*>.*?</iframe>', re.I | re.S)
_JS_PROTO_RE = re.compile(r'javascript:', re.I)

MAX_MESSAGE_LENGTH = 100_000
MAX_MESSAGES_PER_REQUEST = 100


def sanitize_chat_input(text: str) -> str:
    """Sanitize chat input by removing control chars, scripts, and excessive whitespace."""
    result = text
    # Strip dangerous HTML
    result = _SCRIPT_RE.sub("", result)
    result = _IFRAME_RE.sub("", result)
    result = _JS_PROTO_RE.sub("", result)
    # Clean control chars and whitespace
    result = _CONTROL_CHAR_RE.sub("", result)
    result = _EXCESS_NEWLINE_RE.sub("\n\n\n", result)
    result = _EXCESS_SPACE_RE.sub("  ", result)
    # Truncate
    if len(result) > MAX_MESSAGE_LENGTH:
        result = result[:MAX_MESSAGE_LENGTH] + "\n[message truncated]"
    return result.strip()


def validate_chat_messages(messages: list[dict[str, Any]]) -> tuple[bool, str]:
    """Validate a list of chat messages. Returns (valid, error_message)."""
    if not isinstance(messages, list):
        return False, "messages must be a list"
    if len(messages) > MAX_MESSAGES_PER_REQUEST:
        return False, f"too many messages (max {MAX_MESSAGES_PER_REQUEST})"
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict):
            return False, f"message {i} must be an object"
        role = msg.get("role")
        if role not in ("user", "assistant", "system", "tool"):
            return False, f"message {i} has invalid role: {role}"
    return True, ""


# ─── agent-event-assistant-text.ts ───

def extract_assistant_text(content: Any) -> str:
    """Extract text from agent assistant message content."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text", "")))
        return "\n".join(parts)
    return ""


# ─── agent-prompt.ts ───

def build_agent_prompt(
    system_prompt: str,
    context_additions: list[str] | None = None,
) -> str:
    """Build the full agent prompt by combining system prompt and context."""
    parts = [system_prompt]
    if context_additions:
        parts.extend(a for a in context_additions if a and a.strip())
    return "\n\n".join(parts)


# ─── assistant-identity.ts ───

DEFAULT_ASSISTANT_NAME = "OpenClaw"
DEFAULT_ASSISTANT_EMOJI = "🐾"


def resolve_assistant_identity(cfg: dict[str, Any] | None = None) -> dict[str, str]:
    """Resolve assistant display identity from config."""
    if not cfg:
        return {"name": DEFAULT_ASSISTANT_NAME, "emoji": DEFAULT_ASSISTANT_EMOJI}
    identity = cfg.get("assistant", {})
    if not isinstance(identity, dict):
        return {"name": DEFAULT_ASSISTANT_NAME, "emoji": DEFAULT_ASSISTANT_EMOJI}
    return {
        "name": str(identity.get("name", DEFAULT_ASSISTANT_NAME)),
        "emoji": str(identity.get("emoji", DEFAULT_ASSISTANT_EMOJI)),
    }
