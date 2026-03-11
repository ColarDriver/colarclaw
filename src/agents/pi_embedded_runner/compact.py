"""Pi embedded runner compaction — ported from bk/src/agents/pi-embedded-runner/compact.ts."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("openclaw.agents.pi_embedded_runner.compact")


@dataclass
class CompactionResult:
    compacted: bool = False
    entries_removed: int = 0
    tokens_saved: int = 0
    summary: str | None = None


@dataclass
class CompactionConfig:
    threshold_ratio: float = 0.8
    min_entries_to_keep: int = 4
    max_summary_tokens: int = 2000
    enabled: bool = True


def should_compact(
    total_tokens: int,
    context_window: int,
    config: CompactionConfig | None = None,
) -> bool:
    cfg = config or CompactionConfig()
    if not cfg.enabled:
        return False
    return total_tokens > (context_window * cfg.threshold_ratio)


def compact_history(
    entries: list[dict[str, Any]],
    config: CompactionConfig | None = None,
) -> CompactionResult:
    cfg = config or CompactionConfig()
    if len(entries) <= cfg.min_entries_to_keep:
        return CompactionResult()

    # Keep last N entries, summarize the rest
    keep_count = max(cfg.min_entries_to_keep, len(entries) // 2)
    removed = entries[:len(entries) - keep_count]
    entries[:] = entries[-keep_count:]

    return CompactionResult(
        compacted=True,
        entries_removed=len(removed),
    )
