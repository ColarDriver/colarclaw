"""Pi embedded runner history — ported from bk/src/agents/pi-embedded-runner/history.ts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HistoryEntry:
    role: str = ""
    content: Any = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class SessionHistory:
    entries: list[HistoryEntry] = field(default_factory=list)
    total_tokens: int = 0

    def append(self, entry: HistoryEntry) -> None:
        self.entries.append(entry)

    def truncate(self, max_entries: int) -> list[HistoryEntry]:
        if len(self.entries) <= max_entries:
            return []
        removed = self.entries[:len(self.entries) - max_entries]
        self.entries = self.entries[-max_entries:]
        return removed

    def clear(self) -> None:
        self.entries.clear()
        self.total_tokens = 0

    @property
    def length(self) -> int:
        return len(self.entries)
