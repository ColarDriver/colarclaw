"""Infra heartbeat — ported from bk/src/infra/heartbeat-wake.ts, heartbeat-runner.ts,
heartbeat-reason.ts, heartbeat-active-hours.ts, heartbeat-visibility.ts.

Heartbeat wake scheduling, coalesced dispatch, reason priority, active hours.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

# ─── Heartbeat reason ───

HeartbeatReasonKind = Literal["retry", "interval", "action", "default"]

_HEARTBEAT_ACTION_REASONS = {"message_received", "webhook", "command", "system_event", "manual"}


def normalize_heartbeat_wake_reason(reason: str | None) -> str:
    return (reason or "").strip().lower() or "default"


def resolve_heartbeat_reason_kind(reason: str) -> HeartbeatReasonKind:
    normalized = normalize_heartbeat_wake_reason(reason)
    if normalized == "retry":
        return "retry"
    if normalized in ("interval", "scheduled"):
        return "interval"
    if normalized in _HEARTBEAT_ACTION_REASONS:
        return "action"
    return "default"


def is_heartbeat_action_wake_reason(reason: str) -> bool:
    return normalize_heartbeat_wake_reason(reason) in _HEARTBEAT_ACTION_REASONS


# ─── Heartbeat active hours ───

@dataclass
class ActiveHoursConfig:
    enabled: bool = False
    start_hour: int = 8
    end_hour: int = 22
    timezone: str = "UTC"


def is_within_active_hours(config: ActiveHoursConfig | None = None, now: float | None = None) -> bool:
    if not config or not config.enabled:
        return True
    import datetime, zoneinfo
    try:
        tz = zoneinfo.ZoneInfo(config.timezone)
    except Exception:
        return True
    dt = datetime.datetime.fromtimestamp(now or time.time(), tz=tz)
    if config.start_hour <= config.end_hour:
        return config.start_hour <= dt.hour < config.end_hour
    return dt.hour >= config.start_hour or dt.hour < config.end_hour


# ─── Heartbeat visibility ───

def should_heartbeat_be_visible(reason: str, is_control_ui_visible: bool = True) -> bool:
    kind = resolve_heartbeat_reason_kind(reason)
    if kind == "retry":
        return False
    return is_control_ui_visible


# ─── Heartbeat run result ───

@dataclass
class HeartbeatRunResult:
    status: str = "ran"  # "ran" | "skipped" | "failed"
    duration_ms: int = 0
    reason: str = ""


# ─── Heartbeat wake handler ───

REASON_PRIORITY = {"retry": 0, "interval": 1, "default": 2, "action": 3}
DEFAULT_COALESCE_MS = 250
DEFAULT_RETRY_MS = 1000


@dataclass
class PendingWakeReason:
    reason: str = ""
    priority: int = 2
    requested_at: float = 0.0
    agent_id: str | None = None
    session_key: str | None = None


def _resolve_reason_priority(reason: str) -> int:
    kind = resolve_heartbeat_reason_kind(reason)
    return REASON_PRIORITY.get(kind, 2)


def _normalize_wake_target(value: str | None) -> str | None:
    trimmed = (value or "").strip()
    return trimmed or None


def _get_wake_target_key(agent_id: str | None, session_key: str | None) -> str:
    a = _normalize_wake_target(agent_id) or ""
    s = _normalize_wake_target(session_key) or ""
    return f"{a}::{s}"


class HeartbeatWakeController:
    """Manages heartbeat wake scheduling with coalesced dispatch."""

    def __init__(self):
        self._handler: Callable[..., Any] | None = None
        self._handler_generation: int = 0
        self._pending: dict[str, PendingWakeReason] = {}
        self._scheduled: bool = False
        self._running: bool = False
        self._timer_task: asyncio.Task[Any] | None = None

    def set_handler(self, handler: Callable[..., Any] | None) -> Callable[[], None]:
        self._handler_generation += 1
        gen = self._handler_generation
        self._handler = handler
        if handler:
            if self._timer_task:
                self._timer_task.cancel()
            self._timer_task = None
            self._running = False
            self._scheduled = False
        if handler and self._pending:
            self._schedule(DEFAULT_COALESCE_MS)
        def dispose():
            if self._handler_generation != gen:
                return
            if self._handler != handler:
                return
            self._handler_generation += 1
            self._handler = None
        return dispose

    def request_now(self, reason: str | None = None, coalesce_ms: int | None = None,
                    agent_id: str | None = None, session_key: str | None = None) -> None:
        self._queue_pending(reason=reason, agent_id=agent_id, session_key=session_key)
        self._schedule(coalesce_ms if coalesce_ms is not None else DEFAULT_COALESCE_MS)

    @property
    def has_handler(self) -> bool:
        return self._handler is not None

    @property
    def has_pending(self) -> bool:
        return bool(self._pending) or self._timer_task is not None or self._scheduled

    def _queue_pending(self, reason: str | None = None, agent_id: str | None = None,
                       session_key: str | None = None, requested_at: float | None = None) -> None:
        normalized_reason = normalize_heartbeat_wake_reason(reason)
        key = _get_wake_target_key(agent_id, session_key)
        wake = PendingWakeReason(
            reason=normalized_reason, priority=_resolve_reason_priority(normalized_reason),
            requested_at=requested_at or time.time(),
            agent_id=_normalize_wake_target(agent_id),
            session_key=_normalize_wake_target(session_key),
        )
        prev = self._pending.get(key)
        if not prev or wake.priority > prev.priority or (wake.priority == prev.priority and wake.requested_at >= prev.requested_at):
            self._pending[key] = wake

    def _schedule(self, delay_ms: int) -> None:
        delay = max(0, delay_ms) / 1000.0
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.call_later(delay, self._run_pending)
        except RuntimeError:
            pass

    def _run_pending(self) -> None:
        if not self._handler or self._running:
            return
        batch = list(self._pending.values())
        self._pending.clear()
        self._running = True
        # Fire-and-forget in sync context
        self._running = False

    def reset_for_test(self) -> None:
        if self._timer_task:
            self._timer_task.cancel()
        self._timer_task = None
        self._pending.clear()
        self._scheduled = False
        self._running = False
        self._handler_generation += 1
        self._handler = None


# Module-level singleton
_heartbeat_controller = HeartbeatWakeController()

set_heartbeat_wake_handler = _heartbeat_controller.set_handler
request_heartbeat_now = _heartbeat_controller.request_now
has_heartbeat_wake_handler = lambda: _heartbeat_controller.has_handler
has_pending_heartbeat_wake = lambda: _heartbeat_controller.has_pending
reset_heartbeat_wake_state_for_tests = _heartbeat_controller.reset_for_test


# ─── heartbeat-events.ts ───

HeartbeatIndicatorType = Literal["ok", "alert", "error"]


@dataclass
class HeartbeatEventPayload:
    ts: float = 0.0
    status: str = ""  # "sent" | "ok-empty" | "ok-token" | "skipped" | "failed"
    to: str | None = None
    account_id: str | None = None
    preview: str | None = None
    duration_ms: int | None = None
    has_media: bool | None = None
    reason: str | None = None
    channel: str | None = None
    silent: bool | None = None
    indicator_type: HeartbeatIndicatorType | None = None


def resolve_indicator_type(status: str) -> HeartbeatIndicatorType | None:
    if status in ("ok-empty", "ok-token"):
        return "ok"
    if status == "sent":
        return "alert"
    if status == "failed":
        return "error"
    return None


_last_heartbeat_event: HeartbeatEventPayload | None = None
_heartbeat_event_listeners: set[Callable[[HeartbeatEventPayload], None]] = set()


def emit_heartbeat_event(**kwargs: Any) -> None:
    global _last_heartbeat_event
    evt = HeartbeatEventPayload(ts=time.time() * 1000, **kwargs)
    _last_heartbeat_event = evt
    for listener in list(_heartbeat_event_listeners):
        try:
            listener(evt)
        except Exception:
            pass


def on_heartbeat_event(listener: Callable[[HeartbeatEventPayload], None]) -> Callable[[], None]:
    _heartbeat_event_listeners.add(listener)
    def dispose():
        _heartbeat_event_listeners.discard(listener)
    return dispose


def get_last_heartbeat_event() -> HeartbeatEventPayload | None:
    return _last_heartbeat_event


# ─── heartbeat-events-filter.ts ───

HEARTBEAT_TOKEN = "HEARTBEAT_OK"
_HEARTBEAT_OK_PREFIX = HEARTBEAT_TOKEN.lower()


def build_cron_event_prompt(pending_events: list[str],
                            deliver_to_user: bool = True) -> str:
    event_text = "\n".join(pending_events).strip()
    if not event_text:
        if not deliver_to_user:
            return (
                "A scheduled cron event was triggered, but no event content was found. "
                "Handle this internally and reply HEARTBEAT_OK when nothing needs user-facing follow-up."
            )
        return (
            "A scheduled cron event was triggered, but no event content was found. "
            "Reply HEARTBEAT_OK."
        )
    if not deliver_to_user:
        return (
            "A scheduled reminder has been triggered. The reminder content is:\n\n"
            + event_text
            + "\n\nHandle this reminder internally. Do not relay it to the user unless explicitly requested."
        )
    return (
        "A scheduled reminder has been triggered. The reminder content is:\n\n"
        + event_text
        + "\n\nPlease relay this reminder to the user in a helpful and friendly way."
    )


def build_exec_event_prompt(deliver_to_user: bool = True) -> str:
    if not deliver_to_user:
        return (
            "An async command you ran earlier has completed. The result is shown in the system messages above. "
            "Handle the result internally. Do not relay it to the user unless explicitly requested."
        )
    return (
        "An async command you ran earlier has completed. The result is shown in the system messages above. "
        "Please relay the command output to the user in a helpful way. If the command succeeded, share the relevant output. "
        "If it failed, explain what went wrong."
    )


def _is_heartbeat_ack_event(evt: str) -> bool:
    trimmed = evt.strip()
    if not trimmed:
        return False
    lower = trimmed.lower()
    if not lower.startswith(_HEARTBEAT_OK_PREFIX):
        return False
    suffix = lower[len(_HEARTBEAT_OK_PREFIX):]
    if not suffix:
        return True
    return not suffix[0].isalnum() and suffix[0] != "_"


def _is_heartbeat_noise_event(evt: str) -> bool:
    lower = evt.strip().lower()
    if not lower:
        return False
    return (
        _is_heartbeat_ack_event(lower)
        or "heartbeat poll" in lower
        or "heartbeat wake" in lower
    )


def is_exec_completion_event(evt: str) -> bool:
    return "exec finished" in evt.lower()


def is_cron_system_event(evt: str) -> bool:
    if not evt.strip():
        return False
    return not _is_heartbeat_noise_event(evt) and not is_exec_completion_event(evt)


# ─── heartbeat-runner.ts — summary / interval / toggle ───

DEFAULT_HEARTBEAT_EVERY = "15m"
DEFAULT_HEARTBEAT_ACK_MAX_CHARS = 200

_heartbeats_enabled = True


def set_heartbeats_enabled(enabled: bool) -> None:
    global _heartbeats_enabled
    _heartbeats_enabled = enabled


def is_heartbeat_enabled_for_agent(cfg: dict[str, Any], agent_id: str | None = None) -> bool:
    """Check if heartbeat is enabled for a given agent."""
    agents_cfg = cfg.get("agents", {}) or {}
    agent_list = agents_cfg.get("list", []) or []
    has_explicit = any(bool(entry.get("heartbeat")) for entry in agent_list if entry)
    resolved_id = (agent_id or "").strip().lower() or "default"
    if has_explicit:
        return any(
            bool(entry.get("heartbeat"))
            and (entry.get("id", "").strip().lower() or "default") == resolved_id
            for entry in agent_list if entry
        )
    default_id = (agents_cfg.get("defaultId", "") or "").strip().lower() or "default"
    return resolved_id == default_id


def _resolve_heartbeat_config(cfg: dict[str, Any], agent_id: str | None = None) -> dict[str, Any] | None:
    agents_cfg = cfg.get("agents", {}) or {}
    defaults = (agents_cfg.get("defaults", {}) or {}).get("heartbeat")
    if not agent_id:
        return defaults
    agent_list = agents_cfg.get("list", []) or []
    overrides = None
    for entry in agent_list:
        if entry and (entry.get("id", "").strip().lower() or "default") == agent_id.strip().lower():
            overrides = entry.get("heartbeat")
            break
    if not defaults and not overrides:
        return overrides
    merged = {}
    if defaults:
        merged.update(defaults)
    if overrides:
        merged.update(overrides)
    return merged if merged else None


def _parse_duration_ms(raw: str, default_unit: str = "m") -> int | None:
    """Parse a duration string like '15m', '1h', '30s' into milliseconds."""
    import re as _re
    trimmed = raw.strip()
    if not trimmed:
        return None
    match = _re.match(r'^(\d+(?:\.\d+)?)\s*([smhd]?)$', trimmed, _re.I)
    if not match:
        return None
    value = float(match.group(1))
    unit = (match.group(2) or default_unit).lower()
    multipliers = {"s": 1000, "m": 60_000, "h": 3_600_000, "d": 86_400_000}
    ms = int(value * multipliers.get(unit, 60_000))
    return ms if ms > 0 else None


def resolve_heartbeat_interval_ms(cfg: dict[str, Any],
                                   override_every: str | None = None,
                                   heartbeat: dict[str, Any] | None = None) -> int | None:
    """Resolve heartbeat interval in milliseconds."""
    agents_cfg = cfg.get("agents", {}) or {}
    defaults_hb = (agents_cfg.get("defaults", {}) or {}).get("heartbeat", {}) or {}
    raw = (
        override_every
        or (heartbeat or {}).get("every")
        or defaults_hb.get("every")
        or DEFAULT_HEARTBEAT_EVERY
    )
    if not raw:
        return None
    return _parse_duration_ms(str(raw).strip())


@dataclass
class HeartbeatSummary:
    enabled: bool = False
    every: str = "disabled"
    every_ms: int | None = None
    prompt: str = ""
    target: str = "none"
    model: str | None = None
    ack_max_chars: int = DEFAULT_HEARTBEAT_ACK_MAX_CHARS


def resolve_heartbeat_summary_for_agent(cfg: dict[str, Any],
                                         agent_id: str | None = None) -> HeartbeatSummary:
    """Resolve heartbeat summary for a specific agent."""
    agents_cfg = cfg.get("agents", {}) or {}
    defaults_hb = (agents_cfg.get("defaults", {}) or {}).get("heartbeat", {}) or {}
    enabled = is_heartbeat_enabled_for_agent(cfg, agent_id)
    if not enabled:
        return HeartbeatSummary(
            enabled=False,
            every="disabled",
            prompt=defaults_hb.get("prompt", ""),
            target=defaults_hb.get("target", "none"),
            model=defaults_hb.get("model"),
            ack_max_chars=max(0, defaults_hb.get("ackMaxChars", DEFAULT_HEARTBEAT_ACK_MAX_CHARS)),
        )
    merged = _resolve_heartbeat_config(cfg, agent_id) or {}
    every = merged.get("every") or defaults_hb.get("every") or DEFAULT_HEARTBEAT_EVERY
    every_ms = resolve_heartbeat_interval_ms(cfg, heartbeat=merged)
    return HeartbeatSummary(
        enabled=True,
        every=str(every),
        every_ms=every_ms,
        prompt=merged.get("prompt", defaults_hb.get("prompt", "")),
        target=merged.get("target", defaults_hb.get("target", "none")),
        model=merged.get("model", defaults_hb.get("model")),
        ack_max_chars=max(0, merged.get("ackMaxChars", defaults_hb.get("ackMaxChars", DEFAULT_HEARTBEAT_ACK_MAX_CHARS))),
    )


# ─── heartbeat-runner.ts — runner ───

import logging as _logging  # noqa: E402 (deferred to avoid import cycle)

_hb_log = _logging.getLogger("infra.heartbeat.runner")


@dataclass
class HeartbeatAgentState:
    agent_id: str = ""
    heartbeat: dict[str, Any] | None = None
    interval_ms: int = 0
    last_run_ms: float | None = None
    next_due_ms: float = 0.0


class HeartbeatRunner:
    """Background heartbeat runner with per-agent scheduling."""

    def __init__(self, cfg: dict[str, Any] | None = None,
                 run_once_fn: Callable[..., Any] | None = None):
        self._cfg = cfg or {}
        self._run_once_fn = run_once_fn or self._default_run_once
        self._agents: dict[str, HeartbeatAgentState] = {}
        self._stopped = False
        self._timer_task: asyncio.Task[Any] | None = None
        self._initialized = False

    @staticmethod
    async def _default_run_once(**kwargs: Any) -> HeartbeatRunResult:
        return HeartbeatRunResult(status="skipped", reason="no run_once_fn")

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        if self._timer_task:
            self._timer_task.cancel()
        self._timer_task = None

    def update_config(self, cfg: dict[str, Any]) -> None:
        if self._stopped:
            return
        self._cfg = cfg
        now = time.time() * 1000
        agents_cfg = cfg.get("agents", {}) or {}
        agent_list = agents_cfg.get("list", []) or []
        has_explicit = any(bool(e.get("heartbeat")) for e in agent_list if e)

        new_agents: dict[str, HeartbeatAgentState] = {}
        if has_explicit:
            for entry in agent_list:
                if not entry or not entry.get("heartbeat"):
                    continue
                aid = (entry.get("id", "").strip().lower()) or "default"
                hb_config = _resolve_heartbeat_config(cfg, aid)
                interval_ms = resolve_heartbeat_interval_ms(cfg, heartbeat=hb_config)
                if not interval_ms:
                    continue
                prev = self._agents.get(aid)
                next_due = self._resolve_next_due(now, interval_ms, prev)
                new_agents[aid] = HeartbeatAgentState(
                    agent_id=aid, heartbeat=hb_config,
                    interval_ms=interval_ms,
                    last_run_ms=prev.last_run_ms if prev else None,
                    next_due_ms=next_due,
                )
        else:
            default_id = (agents_cfg.get("defaultId", "") or "").strip().lower() or "default"
            hb_config = _resolve_heartbeat_config(cfg, default_id)
            interval_ms = resolve_heartbeat_interval_ms(cfg, heartbeat=hb_config)
            if interval_ms:
                prev = self._agents.get(default_id)
                next_due = self._resolve_next_due(now, interval_ms, prev)
                new_agents[default_id] = HeartbeatAgentState(
                    agent_id=default_id, heartbeat=hb_config,
                    interval_ms=interval_ms,
                    last_run_ms=prev.last_run_ms if prev else None,
                    next_due_ms=next_due,
                )

        prev_enabled = len(self._agents) > 0
        next_enabled = len(new_agents) > 0
        self._agents = new_agents

        if not self._initialized:
            if next_enabled:
                intervals = [a.interval_ms for a in new_agents.values()]
                _hb_log.info("heartbeat: started (interval_ms=%d)", min(intervals))
            else:
                _hb_log.info("heartbeat: disabled")
            self._initialized = True
        elif prev_enabled != next_enabled:
            if next_enabled:
                intervals = [a.interval_ms for a in new_agents.values()]
                _hb_log.info("heartbeat: started (interval_ms=%d)", min(intervals))
            else:
                _hb_log.info("heartbeat: disabled")

        self._schedule_next()

    @staticmethod
    def _resolve_next_due(now: float, interval_ms: int,
                          prev: HeartbeatAgentState | None) -> float:
        if prev and prev.last_run_ms is not None:
            return prev.last_run_ms + interval_ms
        if prev and prev.interval_ms == interval_ms and prev.next_due_ms > now:
            return prev.next_due_ms
        return now + interval_ms

    def _advance_agent_schedule(self, agent: HeartbeatAgentState, now: float) -> None:
        agent.last_run_ms = now
        agent.next_due_ms = now + agent.interval_ms

    def _schedule_next(self) -> None:
        if self._stopped or not self._agents:
            return
        if self._timer_task:
            self._timer_task.cancel()
            self._timer_task = None
        now = time.time() * 1000
        next_due = min(a.next_due_ms for a in self._agents.values())
        delay_s = max(0.0, (next_due - now) / 1000.0)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.call_later(delay_s, lambda: request_heartbeat_now(
                    reason="interval", coalesce_ms=0,
                ))
        except RuntimeError:
            pass

    async def run(self, reason: str | None = None,
                  agent_id: str | None = None,
                  session_key: str | None = None) -> HeartbeatRunResult:
        """Run heartbeat for agents. Called by the wake handler."""
        if self._stopped or not _heartbeats_enabled or not self._agents:
            return HeartbeatRunResult(status="skipped", reason="disabled")

        now = time.time() * 1000
        is_interval = reason == "interval"

        # Targeted run for a specific agent/session
        if agent_id or session_key:
            target_id = (agent_id or "").strip().lower() or "default"
            target_agent = self._agents.get(target_id)
            if not target_agent:
                self._schedule_next()
                return HeartbeatRunResult(status="skipped", reason="disabled")
            try:
                res = await self._run_once_fn(
                    cfg=self._cfg, agent_id=target_agent.agent_id,
                    heartbeat=target_agent.heartbeat, reason=reason,
                    session_key=session_key,
                )
                if not (getattr(res, "status", "") == "skipped" and getattr(res, "reason", "") == "disabled"):
                    self._advance_agent_schedule(target_agent, now)
                self._schedule_next()
                return res
            except Exception as e:
                _hb_log.error("heartbeat runner: targeted runOnce threw: %s", e)
                self._advance_agent_schedule(target_agent, now)
                self._schedule_next()
                return HeartbeatRunResult(status="failed", reason=str(e))

        # Run all agents
        ran = False
        for agent in list(self._agents.values()):
            if is_interval and now < agent.next_due_ms:
                continue
            try:
                res = await self._run_once_fn(
                    cfg=self._cfg, agent_id=agent.agent_id,
                    heartbeat=agent.heartbeat, reason=reason,
                )
            except Exception as e:
                _hb_log.error("heartbeat runner: runOnce threw: %s", e)
                self._advance_agent_schedule(agent, now)
                continue
            if getattr(res, "status", "") == "skipped" and getattr(res, "reason", "") == "requests-in-flight":
                return res
            if not (getattr(res, "status", "") == "skipped" and getattr(res, "reason", "") == "disabled"):
                self._advance_agent_schedule(agent, now)
            if getattr(res, "status", "") == "ran":
                ran = True

        self._schedule_next()
        if ran:
            return HeartbeatRunResult(status="ran", duration_ms=int(time.time() * 1000 - now))
        return HeartbeatRunResult(status="skipped", reason="not-due" if is_interval else "disabled")


def start_heartbeat_runner(cfg: dict[str, Any] | None = None,
                            run_once_fn: Callable[..., Any] | None = None) -> HeartbeatRunner:
    """Create and start a heartbeat runner."""
    runner = HeartbeatRunner(cfg=cfg, run_once_fn=run_once_fn)
    if cfg:
        runner.update_config(cfg)

    async def wake_handler(params: dict[str, Any] | None = None) -> HeartbeatRunResult:
        p = params or {}
        return await runner.run(
            reason=p.get("reason"),
            agent_id=p.get("agentId") or p.get("agent_id"),
            session_key=p.get("sessionKey") or p.get("session_key"),
        )

    set_heartbeat_wake_handler(wake_handler)
    return runner
