"""Reply abort — ported from bk/src/auto-reply/reply/abort.ts + abort-cutoff.ts."""
from __future__ import annotations

import re
from typing import Any

ABORT_TRIGGERS = frozenset(["stop", "cancel", "abort", "/stop", "/cancel", "/abort"])


def is_abort_trigger(text: str) -> bool:
    return text.strip().lower() in ABORT_TRIGGERS


def should_abort_reply(text: str | None = None) -> bool:
    if not text:
        return False
    return is_abort_trigger(text)


def resolve_abort_cutoff(
    reply_text: str,
    abort_index: int | None = None,
    max_cutoff_ratio: float = 0.5,
) -> str:
    if abort_index is None or abort_index < 0:
        return reply_text
    cutoff = min(abort_index, int(len(reply_text) * max_cutoff_ratio))
    return reply_text[:cutoff].rstrip() if cutoff > 0 else ""
