"""Infra events — ported from bk/src/infra/agent-events.ts, system-events.ts,
diagnostic-events.ts, diagnostic-flags.ts, heartbeat-events.ts,
heartbeat-events-filter.ts.

Agent event emitter, system event queue, diagnostic bus.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

# ─── Agent events ───

AgentEventStream = Literal["lifecycle", "tool", "assistant", "error"]


@dataclass
class AgentEventPayload:
    run_id: str = ""
    seq: int = 0
    stream: str = ""
    ts: float = 0.0
    data: dict[str, Any] = field(default_factory=dict)
    session_key: str | None = None


@dataclass
class AgentRunContext:
    session_key: str | None = None
    verbose_level: str | None = None
    is_heartbeat: bool = False
    is_control_ui_visible: bool = True


_seq_by_run: dict[str, int] = {}
_agent_listeners: list[Callable[[AgentEventPayload], None]] = []
_run_context_by_id: dict[str, AgentRunContext] = {}


def register_agent_run_context(run_id: str, context: AgentRunContext) -> None:
    if not run_id:
        return
    existing = _run_context_by_id.get(run_id)
    if not existing:
        _run_context_by_id[run_id] = AgentRunContext(
            session_key=context.session_key, verbose_level=context.verbose_level,
            is_heartbeat=context.is_heartbeat, is_control_ui_visible=context.is_control_ui_visible,
        )
        return
    if context.session_key and existing.session_key != context.session_key:
        existing.session_key = context.session_key
    if context.verbose_level and existing.verbose_level != context.verbose_level:
        existing.verbose_level = context.verbose_level
    if context.is_control_ui_visible is not None:
        existing.is_control_ui_visible = context.is_control_ui_visible
    if context.is_heartbeat is not None:
        existing.is_heartbeat = context.is_heartbeat


def get_agent_run_context(run_id: str) -> AgentRunContext | None:
    return _run_context_by_id.get(run_id)


def clear_agent_run_context(run_id: str) -> None:
    _run_context_by_id.pop(run_id, None)


def reset_agent_run_context_for_test() -> None:
    _run_context_by_id.clear()


def emit_agent_event(run_id: str, stream: str, data: dict[str, Any], session_key: str | None = None) -> None:
    next_seq = _seq_by_run.get(run_id, 0) + 1
    _seq_by_run[run_id] = next_seq
    context = _run_context_by_id.get(run_id)
    is_visible = context.is_control_ui_visible if context else True
    evt_session_key = session_key.strip() if session_key and session_key.strip() else None
    resolved_session_key = (evt_session_key or (context.session_key if context else None)) if is_visible else None
    enriched = AgentEventPayload(
        run_id=run_id, seq=next_seq, stream=stream,
        ts=time.time(), data=data, session_key=resolved_session_key,
    )
    for listener in _agent_listeners:
        try:
            listener(enriched)
        except Exception:
            pass


def on_agent_event(listener: Callable[[AgentEventPayload], None]) -> Callable[[], None]:
    _agent_listeners.append(listener)
    def dispose():
        try:
            _agent_listeners.remove(listener)
        except ValueError:
            pass
    return dispose


# ─── System events ───

@dataclass
class SystemEvent:
    text: str = ""
    ts: float = 0.0
    context_key: str | None = None


MAX_SYSTEM_EVENTS = 20


@dataclass
class _SessionQueue:
    queue: list[SystemEvent] = field(default_factory=list)
    last_text: str | None = None
    last_context_key: str | None = None


_system_queues: dict[str, _SessionQueue] = {}


def _require_session_key(key: str | None) -> str:
    trimmed = (key or "").strip()
    if not trimmed:
        raise ValueError("system events require a sessionKey")
    return trimmed


def _normalize_context_key(key: str | None) -> str | None:
    if not key:
        return None
    trimmed = key.strip()
    return trimmed.lower() if trimmed else None


def is_system_event_context_changed(session_key: str, context_key: str | None = None) -> bool:
    key = _require_session_key(session_key)
    existing = _system_queues.get(key)
    normalized = _normalize_context_key(context_key)
    return normalized != (existing.last_context_key if existing else None)


def enqueue_system_event(text: str, session_key: str, context_key: str | None = None) -> bool:
    key = _require_session_key(session_key)
    entry = _system_queues.get(key)
    if entry is None:
        entry = _SessionQueue()
        _system_queues[key] = entry
    cleaned = text.strip()
    if not cleaned:
        return False
    normalized_context_key = _normalize_context_key(context_key)
    entry.last_context_key = normalized_context_key
    if entry.last_text == cleaned:
        return False
    entry.last_text = cleaned
    entry.queue.append(SystemEvent(text=cleaned, ts=time.time(), context_key=normalized_context_key))
    if len(entry.queue) > MAX_SYSTEM_EVENTS:
        entry.queue.pop(0)
    return True


def drain_system_event_entries(session_key: str) -> list[SystemEvent]:
    key = _require_session_key(session_key)
    entry = _system_queues.get(key)
    if not entry or not entry.queue:
        return []
    out = list(entry.queue)
    entry.queue.clear()
    entry.last_text = None
    entry.last_context_key = None
    del _system_queues[key]
    return out


def drain_system_events(session_key: str) -> list[str]:
    return [e.text for e in drain_system_event_entries(session_key)]


def peek_system_event_entries(session_key: str) -> list[SystemEvent]:
    key = _require_session_key(session_key)
    entry = _system_queues.get(key)
    if not entry:
        return []
    return [SystemEvent(text=e.text, ts=e.ts, context_key=e.context_key) for e in entry.queue]


def peek_system_events(session_key: str) -> list[str]:
    return [e.text for e in peek_system_event_entries(session_key)]


def has_system_events(session_key: str) -> bool:
    key = _require_session_key(session_key)
    entry = _system_queues.get(key)
    return bool(entry and entry.queue)


def reset_system_events_for_test() -> None:
    _system_queues.clear()


# ─── Diagnostic events ───

@dataclass
class DiagnosticEvent:
    kind: str = ""
    message: str = ""
    ts: float = 0.0
    metadata: dict[str, Any] | None = None


_diagnostic_listeners: list[Callable[[DiagnosticEvent], None]] = []


def emit_diagnostic_event(kind: str, message: str, metadata: dict[str, Any] | None = None) -> None:
    event = DiagnosticEvent(kind=kind, message=message, ts=time.time(), metadata=metadata)
    for listener in _diagnostic_listeners:
        try:
            listener(event)
        except Exception:
            pass


def on_diagnostic_event(listener: Callable[[DiagnosticEvent], None]) -> Callable[[], None]:
    _diagnostic_listeners.append(listener)
    def dispose():
        try:
            _diagnostic_listeners.remove(listener)
        except ValueError:
            pass
    return dispose


# ─── Diagnostic flags ───

_diagnostic_flags: dict[str, bool] = {}


def set_diagnostic_flag(name: str, value: bool = True) -> None:
    _diagnostic_flags[name] = value


def get_diagnostic_flag(name: str) -> bool:
    return _diagnostic_flags.get(name, False)


def clear_diagnostic_flags() -> None:
    _diagnostic_flags.clear()


# ─── Heartbeat events ───

@dataclass
class HeartbeatEvent:
    reason: str = ""
    agent_id: str | None = None
    session_key: str | None = None
    ts: float = 0.0
    duration_ms: int | None = None
    status: str = ""  # "ran" | "skipped" | "failed"


_heartbeat_listeners: list[Callable[[HeartbeatEvent], None]] = []


def emit_heartbeat_event(event: HeartbeatEvent) -> None:
    for listener in _heartbeat_listeners:
        try:
            listener(event)
        except Exception:
            pass


def on_heartbeat_event(listener: Callable[[HeartbeatEvent], None]) -> Callable[[], None]:
    _heartbeat_listeners.append(listener)
    def dispose():
        try:
            _heartbeat_listeners.remove(listener)
        except ValueError:
            pass
    return dispose


def filter_heartbeat_events(events: list[HeartbeatEvent], include_skipped: bool = False) -> list[HeartbeatEvent]:
    if include_skipped:
        return list(events)
    return [e for e in events if e.status != "skipped"]
