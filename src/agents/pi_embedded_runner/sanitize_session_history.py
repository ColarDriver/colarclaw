"""Pi embedded runner sanitize session history — ported from bk/src/agents/pi-embedded-runner/sanitize-session-history.ts."""
from __future__ import annotations

from typing import Any


def sanitize_session_history(
    messages: list[dict[str, Any]],
    redact_tool_results: bool = False,
) -> list[dict[str, Any]]:
    """Sanitize session history for logging/persistence."""
    sanitized = []
    for msg in messages:
        entry = dict(msg)
        # Strip tool result details if requested
        if redact_tool_results and entry.get("role") == "tool":
            content = entry.get("content", "")
            if isinstance(content, str) and len(content) > 500:
                entry["content"] = content[:500] + "... (truncated)"
        sanitized.append(entry)
    return sanitized
