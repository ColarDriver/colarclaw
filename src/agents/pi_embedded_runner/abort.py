"""Pi embedded runner abort — ported from bk/src/agents/pi-embedded-runner/abort.ts."""
from __future__ import annotations


def is_runner_abort_error(err: BaseException | None) -> bool:
    """Check if an error is an abort-related error for embedded runners."""
    if err is None:
        return False
    name = type(err).__name__
    if name == "AbortError":
        return True
    message = str(err).lower()
    return "aborted" in message or "cancelled" in message
