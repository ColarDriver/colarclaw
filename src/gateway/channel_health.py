"""Gateway channel health — ported from bk/src/gateway/channel-health-monitor.ts,
channel-health-policy.ts, channel-status-patches.ts, server-channels.ts.

Channel health monitoring, automatic recovery, and status tracking.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ─── channel-health-policy.ts ───

@dataclass
class ChannelHealthPolicy:
    """Policy for channel health monitoring."""
    check_interval_ms: int = 60_000
    unhealthy_threshold: int = 3  # consecutive failures before unhealthy
    recovery_threshold: int = 2  # consecutive successes before recovery
    restart_on_unhealthy: bool = True
    max_restart_count: int = 5
    restart_cooldown_ms: int = 300_000  # 5 minutes


DEFAULT_CHANNEL_HEALTH_POLICY = ChannelHealthPolicy()

# Per-channel policy overrides
CHANNEL_HEALTH_OVERRIDES: dict[str, ChannelHealthPolicy] = {
    # WhatsApp needs more restarts due to QR auth resets
    "whatsapp": ChannelHealthPolicy(
        restart_on_unhealthy=True,
        max_restart_count=10,
        restart_cooldown_ms=600_000,
    ),
}


def get_channel_health_policy(channel_id: str) -> ChannelHealthPolicy:
    """Get the health policy for a channel, with overrides."""
    return CHANNEL_HEALTH_OVERRIDES.get(channel_id, DEFAULT_CHANNEL_HEALTH_POLICY)


# ─── channel-status-patches.ts ───

@dataclass
class ChannelStatusPatch:
    """A patch to a channel's status."""
    channel_id: str = ""
    account_id: str = ""
    status: str = ""  # "connected" | "disconnected" | "error" | "initializing"
    error_message: str | None = None
    updated_at_ms: int = 0


# ─── channel-health-monitor.ts ───

@dataclass
class ChannelHealthState:
    """Health state for a single channel."""
    channel_id: str = ""
    account_id: str = ""
    status: str = "unknown"  # "healthy" | "unhealthy" | "degraded" | "unknown"
    last_check_ms: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    total_failures: int = 0
    total_restarts: int = 0
    last_restart_ms: int = 0
    last_error: str | None = None


class ChannelHealthMonitor:
    """Monitors channel health and triggers automatic recovery.

    Tracks consecutive failures/successes per channel, compares against
    policy thresholds, and triggers restarts when appropriate.
    """

    def __init__(
        self,
        *,
        restart_fn: Callable[[str, str], Any] | None = None,
        broadcast_fn: Callable[[str, Any], None] | None = None,
    ) -> None:
        self._states: dict[str, ChannelHealthState] = {}
        self._restart_fn = restart_fn
        self._broadcast = broadcast_fn
        self._monitor_task: asyncio.Task | None = None

    def get_state(self, channel_id: str, account_id: str = "") -> ChannelHealthState:
        key = f"{channel_id}:{account_id}"
        if key not in self._states:
            self._states[key] = ChannelHealthState(
                channel_id=channel_id,
                account_id=account_id,
            )
        return self._states[key]

    def record_success(self, channel_id: str, account_id: str = "") -> None:
        """Record a successful health check or message delivery."""
        state = self.get_state(channel_id, account_id)
        state.consecutive_successes += 1
        state.consecutive_failures = 0
        state.last_check_ms = int(time.time() * 1000)

        policy = get_channel_health_policy(channel_id)
        if (state.status != "healthy"
                and state.consecutive_successes >= policy.recovery_threshold):
            state.status = "healthy"
            state.last_error = None
            logger.info(f"channel {channel_id} recovered to healthy")
            if self._broadcast:
                self._broadcast("channel.health", {
                    "channelId": channel_id,
                    "accountId": account_id,
                    "status": "healthy",
                })

    def record_failure(self, channel_id: str, account_id: str = "", error: str = "") -> None:
        """Record a failed health check or message delivery."""
        state = self.get_state(channel_id, account_id)
        state.consecutive_failures += 1
        state.consecutive_successes = 0
        state.total_failures += 1
        state.last_check_ms = int(time.time() * 1000)
        state.last_error = error

        policy = get_channel_health_policy(channel_id)
        if state.consecutive_failures >= policy.unhealthy_threshold:
            if state.status != "unhealthy":
                state.status = "unhealthy"
                logger.warning(f"channel {channel_id} marked unhealthy: {error}")
                if self._broadcast:
                    self._broadcast("channel.health", {
                        "channelId": channel_id,
                        "accountId": account_id,
                        "status": "unhealthy",
                        "error": error,
                    })

            # Auto-restart if policy allows
            if (policy.restart_on_unhealthy
                    and state.total_restarts < policy.max_restart_count):
                now = int(time.time() * 1000)
                if now - state.last_restart_ms > policy.restart_cooldown_ms:
                    self._trigger_restart(channel_id, account_id, state)
        elif state.consecutive_failures >= 1:
            state.status = "degraded"

    def _trigger_restart(
        self,
        channel_id: str,
        account_id: str,
        state: ChannelHealthState,
    ) -> None:
        """Trigger a channel restart."""
        state.total_restarts += 1
        state.last_restart_ms = int(time.time() * 1000)
        state.consecutive_failures = 0
        logger.info(
            f"restarting channel {channel_id} (restart #{state.total_restarts})"
        )
        if self._restart_fn:
            try:
                result = self._restart_fn(channel_id, account_id)
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)
            except Exception as e:
                logger.error(f"channel restart failed: {e}")

    def apply_status_patch(self, patch: ChannelStatusPatch) -> None:
        """Apply a channel status patch."""
        state = self.get_state(patch.channel_id, patch.account_id)
        if patch.status == "connected":
            self.record_success(patch.channel_id, patch.account_id)
        elif patch.status in ("disconnected", "error"):
            self.record_failure(
                patch.channel_id,
                patch.account_id,
                patch.error_message or patch.status,
            )

    def get_all_states(self) -> list[ChannelHealthState]:
        return list(self._states.values())

    def clear(self) -> None:
        self._states.clear()
