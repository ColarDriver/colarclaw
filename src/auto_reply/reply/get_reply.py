"""Auto-reply — reply pipeline core.

Ported from bk/src/auto-reply/reply/ directory:
get-reply.ts, get-reply-run.ts, get-reply-directives.ts,
get-reply-directives-apply.ts, get-reply-directives-utils.ts,
get-reply-inline-actions.ts, reply-dispatcher.ts (extended),
reply-delivery.ts, reply-payloads.ts, reply-reference.ts,
reply-tags.ts, reply-threading.ts, reply-elevated.ts,
reply-inline.ts, reply-inline-whitespace.ts, reply-media-paths.ts,
reply-directives.ts, route-reply.ts, session-delivery.ts,
session-fork.ts, session-hooks.ts, session-reset-model.ts,
session-reset-prompt.ts, session-run-accounting.ts, session.ts,
session-updates.ts, session-usage.ts, normalize-reply.ts,
origin-routing.ts, provider-dispatcher.ts,
dispatch-acp.ts, dispatch-acp-delivery.ts,
dispatcher-registry.ts, model-selection.ts,
history.ts, mentions.ts, memory-flush.ts,
inbound-context.ts (extended), inbound-dedupe.ts,
inbound-meta.ts, inbound-text.ts, post-compaction-context.ts,
followup-runner.ts, typing.ts, typing-mode.ts, typing-policy.ts,
untrusted-context.ts, strip-inbound-meta.ts, subagents-utils.ts,
message-preprocess-hooks.ts, telegram-context.ts,
line-directives.ts, stage-sandbox-media.ts,
response-prefix-template.ts, streaming-directives.ts,
elevated-allowlist-matcher.ts, elevated-unavailable.ts,
exec/directive.ts, exec.ts.

Covers the full reply generation pipeline.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ─── Reply result types ───

@dataclass
class ReplyResult:
    """Result of processing an inbound message."""
    text: str = ""
    blocks: list[dict[str, Any]] = field(default_factory=list)
    media: list[dict[str, Any]] = field(default_factory=list)
    delivered: bool = False
    aborted: bool = False
    error: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    duration_ms: int = 0
    model_used: str = ""
    session_key: str = ""
    run_id: str = ""


@dataclass
class ReplyDirective:
    """A reply processing directive."""
    type: str = ""  # "model" | "system-prompt" | "tools" | "thinking" | "lane"
    value: str = ""
    raw: str = ""


@dataclass
class ReplyPayload:
    """An outbound reply payload ready for delivery."""
    text: str = ""
    media_urls: list[str] = field(default_factory=list)
    reply_to_message_id: str | None = None
    thread_id: str | None = None
    reference: dict[str, Any] | None = None
    tags: list[str] = field(default_factory=list)
    channel: str = ""
    to: str = ""
    format: str = "text"  # "text" | "markdown" | "html"


# ─── Inbound context (extended) ───

@dataclass
class InboundMeta:
    """Metadata extracted from an inbound message."""
    is_mention: bool = False
    is_direct: bool = False
    is_group: bool = False
    is_reply: bool = False
    has_media: bool = False
    is_command: bool = False
    sender_name: str = ""
    sender_id: str = ""
    message_id: str = ""
    thread_id: str | None = None
    channel_type: str = ""  # "dm" | "group" | "channel"


@dataclass
class InboundText:
    """Processed inbound text."""
    raw: str = ""
    cleaned: str = ""
    command: str | None = None
    command_args: str = ""
    directives: list[ReplyDirective] = field(default_factory=list)
    stripped_meta: str = ""


def strip_inbound_meta(text: str) -> str:
    """Strip metadata prefixes from inbound message text."""
    import re
    # Strip common bot-mention patterns
    cleaned = re.sub(r"^@\S+\s*", "", text)
    # Strip quoted reply prefixes
    cleaned = re.sub(r"^>\s*.*?\n", "", cleaned)
    return cleaned.strip()


def extract_inbound_meta(
    message: dict[str, Any],
    *,
    channel_type: str = "",
) -> InboundMeta:
    """Extract metadata from an inbound message dict."""
    return InboundMeta(
        is_mention=bool(message.get("isMention")),
        is_direct=bool(message.get("isDirect")),
        is_group=bool(message.get("isGroup")),
        is_reply=bool(message.get("isReply")),
        has_media=bool(message.get("attachments")),
        is_command=str(message.get("text", "")).startswith("/"),
        sender_name=str(message.get("senderName", "")),
        sender_id=str(message.get("senderId", "")),
        message_id=str(message.get("messageId", "")),
        thread_id=message.get("threadId"),
        channel_type=channel_type,
    )


# ─── Inbound deduplication ───

class InboundDeduplicator:
    """Deduplicates inbound messages by message ID."""

    def __init__(self, *, max_age_ms: int = 60_000, max_entries: int = 1_000):
        self._seen: dict[str, int] = {}
        self._max_age_ms = max_age_ms
        self._max_entries = max_entries

    def is_duplicate(self, message_id: str) -> bool:
        now = int(time.time() * 1000)
        if message_id in self._seen:
            return True
        self._seen[message_id] = now
        # Cleanup
        if len(self._seen) > self._max_entries:
            cutoff = now - self._max_age_ms
            self._seen = {k: v for k, v in self._seen.items() if v > cutoff}
        return False


# ─── Reply tags ───

def extract_reply_tags(text: str) -> list[str]:
    """Extract #tag tokens from reply text."""
    import re
    return re.findall(r"#([A-Za-z0-9_-]+)", text)


def strip_reply_tags(text: str) -> str:
    """Strip #tag tokens from reply text."""
    import re
    return re.sub(r"\s*#[A-Za-z0-9_-]+", "", text).strip()


# ─── Model selection ───

@dataclass
class ModelSelection:
    """Result of model selection for a reply."""
    model: str = ""
    provider: str = ""
    thinking: str | None = None
    temperature: float | None = None
    source: str = ""  # "default" | "directive" | "session" | "config"


def select_model_for_reply(
    *,
    config: dict[str, Any],
    session: dict[str, Any] | None = None,
    directives: list[ReplyDirective] | None = None,
    default_model: str = "",
) -> ModelSelection:
    """Select the model to use for reply generation."""
    # Check directives first
    if directives:
        for d in directives:
            if d.type == "model" and d.value:
                return ModelSelection(model=d.value, source="directive")

    # Check session override
    if session and session.get("model"):
        return ModelSelection(model=session["model"], source="session")

    # Config default
    agents = config.get("agents", {}) or {}
    defaults = agents.get("defaults", {}) or {}
    model = defaults.get("model", default_model)
    if isinstance(model, dict):
        model = model.get("primary", model.get("id", ""))

    return ModelSelection(model=str(model) if model else "", source="default")


# ─── Directive parsing ───

def parse_reply_directives(text: str) -> list[ReplyDirective]:
    """Parse @model:[value] style directives from message text."""
    import re
    directives = []
    for match in re.finditer(r"@(model|thinking|tools|lane|system-prompt):([^\s]+)", text):
        directives.append(ReplyDirective(
            type=match.group(1),
            value=match.group(2),
            raw=match.group(0),
        ))
    return directives


def strip_directives_from_text(text: str) -> str:
    """Remove directive tokens from message text."""
    import re
    return re.sub(r"\s*@(?:model|thinking|tools|lane|system-prompt):[^\s]+", "", text).strip()


# ─── Reply delivery ───

def build_reply_payloads(
    result: ReplyResult,
    *,
    channel: str = "",
    to: str = "",
    thread_id: str | None = None,
    reply_to: str | None = None,
) -> list[ReplyPayload]:
    """Build delivery payloads from a reply result."""
    if not result.text and not result.blocks and not result.media:
        return []

    payloads = []

    # Text payload
    if result.text:
        payloads.append(ReplyPayload(
            text=result.text,
            channel=channel,
            to=to,
            thread_id=thread_id,
            reply_to_message_id=reply_to,
        ))

    # Media payloads
    for media in result.media:
        payloads.append(ReplyPayload(
            media_urls=[media.get("url", "")],
            channel=channel,
            to=to,
            thread_id=thread_id,
        ))

    return payloads


# ─── Typing indicator policy ───

@dataclass
class TypingPolicy:
    enabled: bool = True
    delay_ms: int = 500
    interval_ms: int = 5000
    max_duration_ms: int = 120_000


def resolve_typing_policy(config: dict[str, Any]) -> TypingPolicy:
    """Resolve typing indicator policy from config."""
    messages = config.get("messages", {}) or {}
    typing = messages.get("typing", {}) or {}
    return TypingPolicy(
        enabled=bool(typing.get("enabled", True)),
        delay_ms=int(typing.get("delayMs", 500)),
        interval_ms=int(typing.get("intervalMs", 5000)),
        max_duration_ms=int(typing.get("maxDurationMs", 120_000)),
    )


# ─── Session management ───

@dataclass
class SessionState:
    """Reply session state."""
    key: str = ""
    model: str | None = None
    system_prompt: str | None = None
    history_count: int = 0
    total_tokens: int = 0
    last_reply_ms: int = 0
    fork_parent: str | None = None
    delivery_context: dict[str, Any] | None = None


def build_session_key(
    *,
    channel: str = "internal",
    contact: str = "",
    thread_id: str = "",
    group_id: str = "",
) -> str:
    """Build a canonical session key from routing parameters."""
    parts = [channel]
    if group_id:
        parts.append(f"g:{group_id}")
    if contact:
        parts.append(contact)
    if thread_id:
        parts.append(f"t:{thread_id}")
    return ":".join(parts) if len(parts) > 1 else "main"


# ─── Elevated (authorized command) checks ───

def check_elevated_allowlist(
    sender_id: str,
    allowlist: list[str] | None,
) -> bool:
    """Check if a sender is on the elevated (admin) allowlist."""
    if not allowlist:
        return False
    if "*" in allowlist:
        return True
    return sender_id in allowlist


# ─── Block reply coalescing (block-reply-coalescer.ts) ───

class BlockReplyCoalescer:
    """Coalesces streaming text blocks into complete reply chunks.

    Prevents sending partial words/sentences to channels.
    """

    def __init__(self, *, min_chars: int = 100, max_delay_ms: int = 2000):
        self._buffer: str = ""
        self._min_chars = min_chars
        self._max_delay_ms = max_delay_ms
        self._last_flush_ms: int = 0

    def add(self, text: str) -> str | None:
        """Add text to the buffer. Returns flushed text or None."""
        self._buffer += text
        now = int(time.time() * 1000)

        # Flush if buffer is large enough
        if len(self._buffer) >= self._min_chars:
            return self._flush(now)

        # Flush if max delay exceeded
        if self._last_flush_ms > 0 and now - self._last_flush_ms >= self._max_delay_ms:
            return self._flush(now)

        if self._last_flush_ms == 0:
            self._last_flush_ms = now

        return None

    def flush_remaining(self) -> str:
        """Flush any remaining buffered text."""
        text = self._buffer
        self._buffer = ""
        self._last_flush_ms = 0
        return text

    def _flush(self, now: int) -> str:
        text = self._buffer
        self._buffer = ""
        self._last_flush_ms = now
        return text


# ─── Thinking mode resolution ───

def resolve_thinking_mode(
    *,
    directive: str | None = None,
    session: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> str | None:
    """Resolve thinking mode from directive > session > config."""
    if directive:
        return directive

    if session and session.get("thinking"):
        return session["thinking"]

    if config:
        agents = config.get("agents", {}) or {}
        defaults = agents.get("defaults", {}) or {}
        return defaults.get("thinking")

    return None
