"""ACP spawn parent stream — ported from bk/src/agents/acp-spawn-parent-stream.ts.

Relays stream output from a child ACP process to its parent, handling
logging, progress updates, timeouts, and lifecycle events.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("openclaw.agents.acp_spawn_parent_stream")

DEFAULT_STREAM_TIMEOUT_MS = 300_000  # 5 minutes
PROGRESS_EMIT_INTERVAL_MS = 5_000  # Emit progress every 5 seconds


@dataclass
class StreamRelayOptions:
    timeout_ms: int = DEFAULT_STREAM_TIMEOUT_MS
    on_progress: Callable[[dict[str, Any]], None] | None = None
    on_output: Callable[[str], None] | None = None
    on_error: Callable[[str], None] | None = None
    on_complete: Callable[[dict[str, Any]], None] | None = None


@dataclass
class StreamRelayState:
    started_at: float = field(default_factory=lambda: time.time() * 1000)
    last_activity_at: float = field(default_factory=lambda: time.time() * 1000)
    last_progress_emit_at: float = 0
    total_bytes_received: int = 0
    total_chunks_received: int = 0
    is_complete: bool = False
    is_timed_out: bool = False
    error: str | None = None


class AcpSpawnParentStreamRelay:
    """Relays stream output from a child ACP process to its parent."""

    def __init__(self, options: StreamRelayOptions | None = None):
        self._options = options or StreamRelayOptions()
        self._state = StreamRelayState()
        self._buffer: list[str] = []
        self._timeout_task: asyncio.Task[None] | None = None

    @property
    def state(self) -> StreamRelayState:
        return self._state

    async def start(self) -> None:
        """Start the stream relay with timeout monitoring."""
        self._state = StreamRelayState()
        if self._options.timeout_ms > 0:
            self._timeout_task = asyncio.create_task(self._timeout_monitor())

    async def stop(self) -> None:
        """Stop the stream relay."""
        self._state.is_complete = True
        if self._timeout_task:
            self._timeout_task.cancel()
            try:
                await self._timeout_task
            except asyncio.CancelledError:
                pass
            self._timeout_task = None

    def on_chunk(self, chunk: str) -> None:
        """Process a received chunk of output."""
        if self._state.is_complete or self._state.is_timed_out:
            return

        self._state.last_activity_at = time.time() * 1000
        self._state.total_bytes_received += len(chunk)
        self._state.total_chunks_received += 1
        self._buffer.append(chunk)

        if self._options.on_output:
            self._options.on_output(chunk)

        self._maybe_emit_progress()

    def on_error(self, error: str) -> None:
        """Handle an error from the child process."""
        self._state.error = error
        if self._options.on_error:
            self._options.on_error(error)

    def on_complete(self, result: dict[str, Any] | None = None) -> None:
        """Handle completion of the child process."""
        self._state.is_complete = True
        if self._options.on_complete:
            self._options.on_complete(result or {})

    def get_buffered_output(self) -> str:
        """Get all buffered output."""
        return "".join(self._buffer)

    def clear_buffer(self) -> None:
        """Clear the output buffer."""
        self._buffer.clear()

    def _maybe_emit_progress(self) -> None:
        """Emit progress update if enough time has passed."""
        now = time.time() * 1000
        if now - self._state.last_progress_emit_at < PROGRESS_EMIT_INTERVAL_MS:
            return
        self._state.last_progress_emit_at = now
        if self._options.on_progress:
            self._options.on_progress({
                "total_bytes": self._state.total_bytes_received,
                "total_chunks": self._state.total_chunks_received,
                "elapsed_ms": now - self._state.started_at,
            })

    async def _timeout_monitor(self) -> None:
        """Monitor for stream timeout."""
        while not self._state.is_complete:
            await asyncio.sleep(1.0)
            now = time.time() * 1000
            elapsed = now - self._state.last_activity_at
            if elapsed > self._options.timeout_ms:
                self._state.is_timed_out = True
                self.on_error(
                    f"Stream timed out after {int(elapsed)}ms of inactivity "
                    f"(limit: {self._options.timeout_ms}ms)"
                )
                break


async def start_acp_spawn_parent_stream_relay(
    options: StreamRelayOptions | None = None,
) -> AcpSpawnParentStreamRelay:
    """Create and start a parent stream relay."""
    relay = AcpSpawnParentStreamRelay(options)
    await relay.start()
    return relay
