"""Transcript events — ported from bk/src/sessions/transcript-events.ts.

Pub/sub for session transcript update notifications.
"""
from __future__ import annotations

from typing import Callable

_listeners: set[Callable[[str], None]] = set()


def on_session_transcript_update(listener: Callable[[str], None]) -> Callable[[], None]:
    """Subscribe to transcript update events. Returns unsubscribe function."""
    _listeners.add(listener)
    def unsubscribe() -> None:
        _listeners.discard(listener)
    return unsubscribe


def emit_session_transcript_update(session_file: str) -> None:
    """Emit a transcript update notification."""
    trimmed = session_file.strip()
    if not trimmed:
        return
    for listener in list(_listeners):
        try:
            listener(trimmed)
        except Exception:
            pass
