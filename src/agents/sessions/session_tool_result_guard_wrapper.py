"""Session tool-result guard wrapper.

Inspired by ``bk/src/agents/session-tool-result-guard-wrapper.ts`` and adapted
for Python protocols.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from agents.session_tool_result_guard import install_session_tool_result_guard


@runtime_checkable
class SessionManagerProtocol(Protocol):
    """Minimal session manager protocol required by guard wrapper."""

    def append_message(self, message: dict[str, Any]) -> Any:
        """Append one transcript message."""


@runtime_checkable
class GuardedSessionManagerProtocol(SessionManagerProtocol, Protocol):
    """Session manager protocol after tool-result guard installation."""

    def flush_pending_tool_results(self) -> None:
        """Flush synthetic tool results for pending calls."""

    def clear_pending_tool_results(self) -> None:
        """Clear pending calls without writing synthetic results."""


@dataclass(frozen=True)
class GuardSessionManagerOptions:
    """Options passed through to install_session_tool_result_guard."""

    agent_id: str | None = None
    session_key: str | None = None
    input_provenance: Any | None = None
    allow_synthetic_tool_results: bool | None = None
    allowed_tool_names: list[str] | set[str] | tuple[str, ...] | None = None
    transform_message_for_persistence: Any | None = None
    transform_tool_result_for_persistence: Any | None = None
    before_message_write_hook: Any | None = None


def guard_session_manager(
    session_manager: SessionManagerProtocol,
    opts: GuardSessionManagerOptions | None = None,
) -> GuardedSessionManagerProtocol:
    """Install the session tool-result guard exactly once and return manager."""
    existing_flush = getattr(session_manager, "flush_pending_tool_results", None)
    if callable(existing_flush):
        return session_manager  # type: ignore[return-value]

    options = opts or GuardSessionManagerOptions()
    install_opts: dict[str, Any] = {
        "allow_synthetic_tool_results": (
            True if options.allow_synthetic_tool_results is None else options.allow_synthetic_tool_results
        ),
        "allowed_tool_names": options.allowed_tool_names,
        "transform_message_for_persistence": options.transform_message_for_persistence,
        "transform_tool_result_for_persistence": options.transform_tool_result_for_persistence,
        "before_message_write_hook": options.before_message_write_hook,
    }

    install_session_tool_result_guard(session_manager, install_opts)
    return session_manager  # type: ignore[return-value]


__all__ = [
    "SessionManagerProtocol",
    "GuardedSessionManagerProtocol",
    "GuardSessionManagerOptions",
    "guard_session_manager",
]
