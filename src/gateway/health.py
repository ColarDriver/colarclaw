"""Gateway health — ported from bk/src/gateway/ health files.

Channel health monitoring, health policy, and status patching.
Consolidates: channel-health-monitor.ts, channel-health-policy.ts,
  channel-status-patches.ts.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

HealthStatus = Literal["healthy", "degraded", "unhealthy", "unknown"]


@dataclass
class ChannelHealthSnapshot:
    channel: str = ""
    account_id: str = ""
    status: HealthStatus = "unknown"
    last_check_ms: int = 0
    last_success_ms: int = 0
    consecutive_failures: int = 0
    error: str | None = None


@dataclass
class ChannelHealthPolicy:
    check_interval_ms: int = 60_000
    unhealthy_threshold: int = 3
    degraded_threshold: int = 1
    auto_disable: bool = False


class ChannelHealthMonitor:
    """Track channel health across accounts."""

    def __init__(self, policy: ChannelHealthPolicy | None = None) -> None:
        self._policy = policy or ChannelHealthPolicy()
        self._snapshots: dict[str, ChannelHealthSnapshot] = {}

    def _key(self, channel: str, account_id: str) -> str:
        return f"{channel}:{account_id}"

    def record_success(self, channel: str, account_id: str) -> None:
        key = self._key(channel, account_id)
        now = int(time.time() * 1000)
        snap = self._snapshots.get(key) or ChannelHealthSnapshot(channel=channel, account_id=account_id)
        snap.status = "healthy"
        snap.last_check_ms = now
        snap.last_success_ms = now
        snap.consecutive_failures = 0
        snap.error = None
        self._snapshots[key] = snap

    def record_failure(self, channel: str, account_id: str, error: str = "") -> None:
        key = self._key(channel, account_id)
        now = int(time.time() * 1000)
        snap = self._snapshots.get(key) or ChannelHealthSnapshot(channel=channel, account_id=account_id)
        snap.last_check_ms = now
        snap.consecutive_failures += 1
        snap.error = error
        if snap.consecutive_failures >= self._policy.unhealthy_threshold:
            snap.status = "unhealthy"
        elif snap.consecutive_failures >= self._policy.degraded_threshold:
            snap.status = "degraded"
        self._snapshots[key] = snap

    def get_snapshot(self, channel: str, account_id: str) -> ChannelHealthSnapshot | None:
        return self._snapshots.get(self._key(channel, account_id))

    def get_all_snapshots(self) -> list[ChannelHealthSnapshot]:
        return list(self._snapshots.values())

    def needs_check(self, channel: str, account_id: str) -> bool:
        snap = self.get_snapshot(channel, account_id)
        if not snap:
            return True
        now = int(time.time() * 1000)
        return (now - snap.last_check_ms) >= self._policy.check_interval_ms


# ─── channel-status-patches.ts ───

@dataclass
class ChannelStatusPatch:
    channel: str = ""
    account_id: str = ""
    field: str = ""
    value: Any = None
    applied_at_ms: int = 0


def apply_channel_status_patches(
    status: dict[str, Any],
    patches: list[ChannelStatusPatch],
) -> dict[str, Any]:
    """Apply patches to channel status."""
    result = dict(status)
    for patch in patches:
        if patch.field:
            result[patch.field] = patch.value
    return result
