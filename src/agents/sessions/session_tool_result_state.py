"""Session tool-result pending state shard.

Ported from ``bk/src/agents/session-tool-result-state.ts``.
Tracks pending tool calls and flush trigger conditions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator


@dataclass(frozen=True)
class PendingToolCall:
    """Pending tool call identity and optional tool name."""

    id: str
    name: str | None = None


@dataclass
class PendingToolCallState:
    """Mutable state for pending tool call/result pairing management."""

    _pending: dict[str, str | None] = field(default_factory=dict)

    def size(self) -> int:
        """Return number of currently pending tool call IDs."""
        return len(self._pending)

    def entries(self) -> Iterator[tuple[str, str | None]]:
        """Iterate pending `(tool_call_id, tool_name)` entries."""
        return iter(self._pending.items())

    def get_tool_name(self, tool_call_id: str) -> str | None:
        """Get tracked tool name for pending tool call id."""
        return self._pending.get(tool_call_id)

    def delete(self, tool_call_id: str) -> None:
        """Delete one pending tool call id if present."""
        self._pending.pop(tool_call_id, None)

    def clear(self) -> None:
        """Clear all pending tool call ids."""
        self._pending.clear()

    def track_tool_calls(self, calls: list[PendingToolCall]) -> None:
        """Track newly emitted assistant tool calls as pending."""
        for call in calls:
            self._pending[call.id] = call.name

    def get_pending_ids(self) -> list[str]:
        """Return pending tool call ids in insertion order."""
        return list(self._pending.keys())

    def should_flush_for_sanitized_drop(self) -> bool:
        """Return True when dropping assistant tool calls should flush pending state."""
        return len(self._pending) > 0

    def should_flush_before_non_tool_result(self, next_role: object, tool_call_count: int) -> bool:
        """Return True when non-tool-result message should trigger pending flush."""
        return len(self._pending) > 0 and (tool_call_count == 0 or next_role != "assistant")

    def should_flush_before_new_tool_calls(self, tool_call_count: int) -> bool:
        """Return True when older pending calls must flush before new tool calls."""
        return len(self._pending) > 0 and tool_call_count > 0


def create_pending_tool_call_state() -> PendingToolCallState:
    """Factory matching TS `createPendingToolCallState` behavior."""
    return PendingToolCallState()


__all__ = [
    "PendingToolCall",
    "PendingToolCallState",
    "create_pending_tool_call_state",
]
