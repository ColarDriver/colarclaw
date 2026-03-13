"""Infra channels — ported from bk/src/infra/channel-types.ts,
channel-status.ts, channel-allowlist.ts, channel-routing.ts,
channel-gating.ts, channel-onboarding.ts, channel-health.ts.

Channel infrastructure: types, status, routing, allowlists,
gating, onboarding, health checks.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

logger = logging.getLogger("infra.channels")


# ─── channel-types.ts ───

ChannelType = Literal[
    "telegram", "discord", "slack", "signal", "imessage",
    "whatsapp", "web", "msteams", "matrix", "zalo",
    "zalouser", "voice-call",
]


@dataclass
class ChannelInfo:
    name: str = ""
    type: str = ""
    enabled: bool = False
    connected: bool = False
    account_id: str = ""
    display_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ─── channel-status.ts ───

@dataclass
class ChannelStatus:
    channel: str = ""
    status: str = "disconnected"  # "connected" | "connecting" | "disconnected" | "error"
    error: str | None = None
    last_message_at: float | None = None
    uptime_ms: int = 0
    message_count: int = 0


class ChannelStatusRegistry:
    """Registry for tracking channel status."""

    def __init__(self):
        self._statuses: dict[str, ChannelStatus] = {}
        self._listeners: list[Callable[[ChannelStatus], None]] = []

    def update(self, channel: str, status: str, error: str | None = None) -> None:
        if channel not in self._statuses:
            self._statuses[channel] = ChannelStatus(channel=channel)
        s = self._statuses[channel]
        s.status = status
        s.error = error
        for listener in self._listeners:
            try:
                listener(s)
            except Exception:
                pass

    def get(self, channel: str) -> ChannelStatus | None:
        return self._statuses.get(channel)

    def get_all(self) -> list[ChannelStatus]:
        return list(self._statuses.values())

    def on_change(self, listener: Callable[[ChannelStatus], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        def dispose():
            try:
                self._listeners.remove(listener)
            except ValueError:
                pass
        return dispose

    def record_message(self, channel: str) -> None:
        if channel in self._statuses:
            self._statuses[channel].last_message_at = time.time()
            self._statuses[channel].message_count += 1


# ─── channel-allowlist.ts ───

@dataclass
class ChannelAllowlist:
    enabled: bool = False
    allowed: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)
    default_allow: bool = True


def check_channel_allowed(channel: str, allowlist: ChannelAllowlist | None = None) -> bool:
    """Check if a channel is allowed."""
    if not allowlist or not allowlist.enabled:
        return True
    channel_lower = channel.strip().lower()
    if channel_lower in [b.lower() for b in allowlist.blocked]:
        return False
    if allowlist.allowed:
        return channel_lower in [a.lower() for a in allowlist.allowed]
    return allowlist.default_allow


def check_target_allowed(
    target: str,
    allowed_targets: list[str] | None = None,
    blocked_targets: list[str] | None = None,
) -> bool:
    """Check if a target (user/group) is allowed."""
    t = target.strip().lower()
    if blocked_targets:
        for blocked in blocked_targets:
            if blocked.strip().lower() == t:
                return False
    if allowed_targets is not None:
        return any(a.strip().lower() == t for a in allowed_targets)
    return True


# ─── channel-routing.ts ───

@dataclass
class ChannelRoute:
    pattern: str = ""
    channel: str = ""
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class ChannelRouter:
    """Route messages to channels based on patterns."""

    def __init__(self):
        self._routes: list[ChannelRoute] = []
        self._default_channel: str | None = None

    def add_route(self, pattern: str, channel: str, priority: int = 0) -> None:
        self._routes.append(ChannelRoute(pattern=pattern, channel=channel, priority=priority))
        self._routes.sort(key=lambda r: -r.priority)

    def set_default(self, channel: str) -> None:
        self._default_channel = channel

    def resolve(self, target: str) -> str | None:
        for route in self._routes:
            try:
                if re.match(route.pattern, target, re.I):
                    return route.channel
            except re.error:
                if route.pattern.lower() == target.lower():
                    return route.channel
        return self._default_channel

    def get_routes(self) -> list[ChannelRoute]:
        return list(self._routes)


# ─── channel-gating.ts ───

@dataclass
class ChannelGate:
    channel: str = ""
    gate: str = ""  # "open" | "closed" | "paused"
    reason: str | None = None
    until: float | None = None


_channel_gates: dict[str, ChannelGate] = {}


def set_channel_gate(channel: str, gate: str, reason: str | None = None,
                     duration_s: float | None = None) -> None:
    until = time.time() + duration_s if duration_s else None
    _channel_gates[channel] = ChannelGate(channel=channel, gate=gate, reason=reason, until=until)


def get_channel_gate(channel: str) -> ChannelGate | None:
    gate = _channel_gates.get(channel)
    if gate and gate.until and time.time() > gate.until:
        del _channel_gates[channel]
        return None
    return gate


def is_channel_open(channel: str) -> bool:
    gate = get_channel_gate(channel)
    return gate is None or gate.gate == "open"


def clear_channel_gates() -> None:
    _channel_gates.clear()


# ─── channel-onboarding.ts ───

@dataclass
class ChannelOnboardingStep:
    step: str = ""
    title: str = ""
    description: str = ""
    completed: bool = False
    required: bool = True


@dataclass
class ChannelOnboardingState:
    channel: str = ""
    started: bool = False
    completed: bool = False
    steps: list[ChannelOnboardingStep] = field(default_factory=list)
    current_step: int = 0


def create_onboarding_state(channel: str, steps: list[dict[str, Any]]) -> ChannelOnboardingState:
    return ChannelOnboardingState(
        channel=channel,
        started=True,
        steps=[ChannelOnboardingStep(**s) for s in steps],
    )


def advance_onboarding(state: ChannelOnboardingState) -> bool:
    """Mark current step complete and advance. Returns True if all done."""
    if state.current_step < len(state.steps):
        state.steps[state.current_step].completed = True
        state.current_step += 1
    state.completed = all(s.completed for s in state.steps if s.required)
    return state.completed


# ─── channel-health.ts ───

@dataclass
class ChannelHealthCheck:
    channel: str = ""
    healthy: bool = True
    latency_ms: float | None = None
    last_check_at: float = 0.0
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


async def check_channel_health(
    channel: str,
    probe_fn: Callable[..., Any] | None = None,
) -> ChannelHealthCheck:
    """Run health check on a channel."""
    start = time.time()
    try:
        if probe_fn:
            import asyncio
            result = probe_fn()
            if asyncio.iscoroutine(result):
                result = await result
        latency_ms = (time.time() - start) * 1000
        return ChannelHealthCheck(
            channel=channel, healthy=True,
            latency_ms=round(latency_ms, 1),
            last_check_at=time.time(),
        )
    except Exception as e:
        return ChannelHealthCheck(
            channel=channel, healthy=False,
            error=str(e), last_check_at=time.time(),
        )
