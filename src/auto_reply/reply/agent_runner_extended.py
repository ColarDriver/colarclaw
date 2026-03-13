"""Auto-reply — agent runner and block streaming.

Ported from bk/src/auto-reply/reply/:
agent-runner-execution.ts, agent-runner-helpers.ts,
agent-runner-memory.ts, agent-runner-payloads.ts,
agent-runner-reminder-guard.ts, agent-runner-utils.ts,
block-reply-coalescer.ts, block-reply-pipeline.ts (extended),
block-streaming.ts, abort-cutoff.ts,
acp-reset-target.ts, acp-stream-settings.ts.

Covers agent execution orchestration, streaming block assembly,
abort cutoff, and ACP streaming configuration.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


# ─── Agent runner execution ───

@dataclass
class AgentRunConfig:
    """Configuration for a single agent run."""
    run_id: str = ""
    session_key: str = ""
    agent_id: str = ""
    model: str = ""
    message: str = ""
    system_prompt: str = ""
    thinking: str | None = None
    tools: list[str] | None = None
    max_tokens: int = 8192
    temperature: float | None = None
    timeout_ms: int = 300_000
    workspace_dir: str = ""
    attachments: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AgentRunEvent:
    """An event emitted during an agent run."""
    type: str = ""  # "text" | "tool_use" | "tool_result" | "thinking" | "error" | "done"
    text: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    timestamp_ms: int = 0


class AgentRunnerExecution:
    """Orchestrates a single agent run.

    Manages the lifecycle: init → send → stream → complete/abort.
    """

    def __init__(self, config: AgentRunConfig) -> None:
        self._config = config
        self._aborted = False
        self._started_at_ms = 0
        self._finished = False
        self._accumulated_text = ""
        self._tool_calls: list[dict[str, Any]] = []

    @property
    def run_id(self) -> str:
        return self._config.run_id

    @property
    def is_aborted(self) -> bool:
        return self._aborted

    @property
    def accumulated_text(self) -> str:
        return self._accumulated_text

    def abort(self) -> None:
        """Abort this run."""
        self._aborted = True

    async def execute(self) -> AsyncIterator[AgentRunEvent]:
        """Execute the agent run, yielding events."""
        self._started_at_ms = int(time.time() * 1000)

        # In production, this would call the LLM provider
        # and yield streaming events. This is a skeleton.
        yield AgentRunEvent(
            type="text",
            text="[agent run not wired to provider yet]",
            timestamp_ms=int(time.time() * 1000),
        )
        yield AgentRunEvent(
            type="done",
            timestamp_ms=int(time.time() * 1000),
        )
        self._finished = True

    def check_timeout(self) -> bool:
        """Check if the run has exceeded its timeout."""
        if self._finished or self._started_at_ms == 0:
            return False
        elapsed = int(time.time() * 1000) - self._started_at_ms
        return elapsed > self._config.timeout_ms


# ─── Agent runner helpers ───

def build_agent_run_messages(
    *,
    message: str,
    system_prompt: str = "",
    history: list[dict[str, Any]] | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build the message array for an agent run."""
    messages: list[dict[str, Any]] = []

    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    # Add history
    if history:
        messages.extend(history)

    # Build user message
    user_content: Any = message
    if attachments:
        content_parts: list[dict[str, Any]] = [{"type": "text", "text": message}]
        for att in attachments:
            if att.get("type") == "image":
                content_parts.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": att.get("mimeType", "image/png"),
                        "data": att.get("content", ""),
                    },
                })
            else:
                content_parts.append({
                    "type": "text",
                    "text": f"[Attachment: {att.get('fileName', 'file')}]",
                })
        user_content = content_parts

    messages.append({"role": "user", "content": user_content})
    return messages


# ─── Agent runner memory ───

def should_flush_memory(
    *,
    history_count: int,
    total_tokens: int,
    config: dict[str, Any] | None = None,
) -> bool:
    """Determine if memory should be flushed after this run."""
    mem_config = (config or {}).get("memory", {}) or {}
    if not mem_config.get("enabled"):
        return False
    if not mem_config.get("autoSave", True):
        return False
    # Flush every 10 exchanges by default
    interval = mem_config.get("flushInterval", 10)
    return history_count > 0 and history_count % interval == 0


# ─── Agent runner reminder guard ───

class ReminderGuard:
    """Prevents excessive reminder/heartbeat messages."""

    def __init__(self, *, min_interval_ms: int = 30_000):
        self._min_interval_ms = min_interval_ms
        self._last_reminder: dict[str, int] = {}

    def should_send(self, session_key: str) -> bool:
        now = int(time.time() * 1000)
        last = self._last_reminder.get(session_key, 0)
        if now - last < self._min_interval_ms:
            return False
        self._last_reminder[session_key] = now
        return True

    def reset(self, session_key: str) -> None:
        self._last_reminder.pop(session_key, None)


# ─── Block streaming ───

@dataclass
class StreamBlock:
    """A streaming content block."""
    type: str = "text"  # "text" | "thinking" | "tool_use" | "tool_result"
    text: str = ""
    index: int = 0
    is_final: bool = False


class BlockStreamAssembler:
    """Assembles streaming deltas into complete content blocks."""

    def __init__(self) -> None:
        self._blocks: dict[int, StreamBlock] = {}
        self._current_index = 0

    def add_delta(
        self,
        *,
        index: int = -1,
        block_type: str = "text",
        text: str = "",
        is_final: bool = False,
    ) -> StreamBlock | None:
        """Add a streaming delta. Returns completed block or None."""
        if index < 0:
            index = self._current_index

        if index not in self._blocks:
            self._blocks[index] = StreamBlock(
                type=block_type,
                index=index,
            )

        block = self._blocks[index]
        block.text += text

        if is_final:
            block.is_final = True
            self._current_index = index + 1
            return block

        return None

    def finalize(self) -> list[StreamBlock]:
        """Finalize all remaining blocks."""
        result = []
        for index in sorted(self._blocks.keys()):
            block = self._blocks[index]
            block.is_final = True
            result.append(block)
        self._blocks.clear()
        return result


# ─── Abort cutoff ───

@dataclass
class AbortCutoffConfig:
    """Configuration for abort cutoff behavior."""
    min_chars_before_cutoff: int = 50
    include_partial: bool = True
    add_abort_marker: bool = True
    marker_text: str = "\n\n[generation stopped]"


def apply_abort_cutoff(
    text: str,
    config: AbortCutoffConfig | None = None,
) -> str:
    """Apply cutoff formatting to an aborted response."""
    cfg = config or AbortCutoffConfig()
    if not text:
        return ""
    if len(text) < cfg.min_chars_before_cutoff and not cfg.include_partial:
        return ""
    if cfg.add_abort_marker:
        return text + cfg.marker_text
    return text


# ─── ACP stream settings ───

@dataclass
class AcpStreamSettings:
    """Settings for ACP (Agent Computer Protocol) streaming."""
    enabled: bool = True
    chunk_size: int = 1024
    flush_interval_ms: int = 100
    max_pending_bytes: int = 64 * 1024


def resolve_acp_stream_settings(
    config: dict[str, Any] | None = None,
) -> AcpStreamSettings:
    """Resolve ACP streaming settings from config."""
    acp = (config or {}).get("acp", {}) or {}
    stream = acp.get("streaming", {}) or {}
    return AcpStreamSettings(
        enabled=bool(stream.get("enabled", True)),
        chunk_size=int(stream.get("chunkSize", 1024)),
        flush_interval_ms=int(stream.get("flushIntervalMs", 100)),
        max_pending_bytes=int(stream.get("maxPendingBytes", 64 * 1024)),
    )
