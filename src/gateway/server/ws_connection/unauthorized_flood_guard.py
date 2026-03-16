"""Unauthorized flood guard — ported from openclaw server/ws-connection/unauthorized-flood-guard.ts.

Tracks repeated unauthorized requests on a single WebSocket connection.
After a threshold is crossed, the guard recommends closing the connection.
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_CLOSE_AFTER = 10
DEFAULT_LOG_EVERY = 100


@dataclass
class UnauthorizedFloodDecision:
    should_close: bool
    should_log: bool
    count: int
    suppressed_since_last_log: int


class UnauthorizedFloodGuard:
    """Tracks consecutive unauthorized requests and decides when to close."""

    def __init__(
        self,
        *,
        close_after: int = DEFAULT_CLOSE_AFTER,
        log_every: int = DEFAULT_LOG_EVERY,
    ) -> None:
        self._close_after = max(1, close_after)
        self._log_every = max(1, log_every)
        self._count = 0
        self._suppressed_since_last_log = 0

    def register_unauthorized(self) -> UnauthorizedFloodDecision:
        self._count += 1
        should_close = self._count > self._close_after
        should_log = (
            self._count == 1
            or self._count % self._log_every == 0
            or should_close
        )

        if not should_log:
            self._suppressed_since_last_log += 1
            return UnauthorizedFloodDecision(
                should_close=should_close,
                should_log=False,
                count=self._count,
                suppressed_since_last_log=0,
            )

        suppressed = self._suppressed_since_last_log
        self._suppressed_since_last_log = 0
        return UnauthorizedFloodDecision(
            should_close=should_close,
            should_log=True,
            count=self._count,
            suppressed_since_last_log=suppressed,
        )

    def reset(self) -> None:
        self._count = 0
        self._suppressed_since_last_log = 0


# Error code constant matching OpenClaw's protocol ErrorCodes.INVALID_REQUEST
ERROR_CODE_INVALID_REQUEST = "INVALID_REQUEST"


def is_unauthorized_role_error(error: dict | None) -> bool:
    """Check if *error* is an 'unauthorized role:' rejection."""
    if not error:
        return False
    return (
        error.get("code") == ERROR_CODE_INVALID_REQUEST
        and isinstance(error.get("message"), str)
        and error["message"].startswith("unauthorized role:")
    )
