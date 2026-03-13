"""Cron — extended: service timer, jobs, store, isolated agent execution.

Ported from bk/src/cron/ remaining:
service/timer.ts (~1219行), service/jobs.ts (~900行),
isolated-agent/run.ts (~864行),
isolated-agent/delivery-dispatch.ts (~553行),
normalize.ts (~506行), service/store.ts (~503行),
service/ops.ts (~473行).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── Cron normalization ───

def normalize_cron_schedule(schedule: str) -> str:
    """Normalize a cron schedule string."""
    schedule = schedule.strip()
    
    # Named intervals
    names = {
        "every minute": "* * * * *",
        "every 5 minutes": "*/5 * * * *",
        "every 15 minutes": "*/15 * * * *",
        "every 30 minutes": "*/30 * * * *",
        "every hour": "0 * * * *",
        "every 2 hours": "0 */2 * * *",
        "every 4 hours": "0 */4 * * *",
        "every 6 hours": "0 */6 * * *",
        "every 12 hours": "0 */12 * * *",
        "every day": "0 0 * * *",
        "every week": "0 0 * * 0",
        "every month": "0 0 1 * *",
    }
    if schedule.lower() in names:
        return names[schedule.lower()]
    
    # Standard shortcuts
    shortcuts = {
        "@yearly": "0 0 1 1 *",
        "@annually": "0 0 1 1 *",
        "@monthly": "0 0 1 * *",
        "@weekly": "0 0 * * 0",
        "@daily": "0 0 * * *",
        "@midnight": "0 0 * * *",
        "@hourly": "0 * * * *",
    }
    if schedule.lower() in shortcuts:
        return shortcuts[schedule.lower()]
    
    return schedule


def validate_cron_schedule(schedule: str) -> str | None:
    """Validate a cron schedule. Returns error message or None if valid."""
    from . import parse_cron_expression
    try:
        normalized = normalize_cron_schedule(schedule)
        parse_cron_expression(normalized)
        return None
    except ValueError as e:
        return str(e)


# ─── Job store ───

class CronJobStore:
    """Persistent storage for cron job state."""

    def __init__(self, store_path: str):
        self._store_path = store_path
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if os.path.exists(self._store_path):
            try:
                with open(self._store_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception:
                self._data = {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._store_path), exist_ok=True)
        with open(self._store_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)

    def get_last_run(self, job_id: str) -> int:
        """Get last run time in ms."""
        return int(self._data.get("lastRun", {}).get(job_id, 0))

    def set_last_run(self, job_id: str, timestamp_ms: int) -> None:
        self._data.setdefault("lastRun", {})[job_id] = timestamp_ms
        self._save()

    def get_run_count(self, job_id: str) -> int:
        return int(self._data.get("runCount", {}).get(job_id, 0))

    def increment_run_count(self, job_id: str) -> int:
        self._data.setdefault("runCount", {})
        count = self._data["runCount"].get(job_id, 0) + 1
        self._data["runCount"][job_id] = count
        self._save()
        return count

    def get_history(self, job_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        history = self._data.get("history", {}).get(job_id, [])
        return history[-limit:]

    def add_history(self, job_id: str, entry: dict[str, Any]) -> None:
        self._data.setdefault("history", {}).setdefault(job_id, []).append(entry)
        # Trim
        max_entries = 100
        if len(self._data["history"][job_id]) > max_entries:
            self._data["history"][job_id] = self._data["history"][job_id][-max_entries:]
        self._save()


# ─── Service timer ───

class CronServiceTimer:
    """High-precision cron timer aligned to minute boundaries."""

    def __init__(
        self,
        *,
        drift_tolerance_ms: int = 2000,
        min_interval_ms: int = 55_000,
    ):
        self._drift_tolerance = drift_tolerance_ms
        self._min_interval = min_interval_ms
        self._next_tick_ms: int = 0
        self._running = False

    def _calculate_next_tick(self) -> int:
        """Calculate the next minute boundary."""
        now_ms = int(time.time() * 1000)
        current_minute = (now_ms // 60_000) * 60_000
        next_minute = current_minute + 60_000
        return next_minute

    async def run(self, on_tick: Any) -> None:
        """Run the timer loop."""
        self._running = True
        while self._running:
            self._next_tick_ms = self._calculate_next_tick()
            now_ms = int(time.time() * 1000)
            wait_ms = max(0, self._next_tick_ms - now_ms)
            
            if wait_ms > 0:
                await asyncio.sleep(wait_ms / 1000)
            
            # Check drift
            actual_ms = int(time.time() * 1000)
            drift = abs(actual_ms - self._next_tick_ms)
            if drift > self._drift_tolerance:
                logger.warning(f"Timer drift: {drift}ms (tolerance: {self._drift_tolerance}ms)")
            
            try:
                result = on_tick()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Tick handler error: {e}")

    def stop(self) -> None:
        self._running = False


# ─── Service ops ───

class CronServiceOps:
    """Cron service operations."""

    def __init__(self, store: CronJobStore):
        self._store = store

    def should_run(self, job_id: str, *, schedule: str, now_ms: int = 0) -> bool:
        """Check if a job should run at the current time."""
        from . import parse_cron_expression
        now_ms = now_ms or int(time.time() * 1000)
        last_run = self._store.get_last_run(job_id)
        
        # Don't run more than once per minute
        if now_ms - last_run < 55_000:
            return False
        
        normalized = normalize_cron_schedule(schedule)
        expr = parse_cron_expression(normalized)
        now_struct = time.localtime(now_ms / 1000)
        return expr.matches_time(now_struct)

    def record_run(self, job_id: str, *, success: bool, duration_ms: int = 0, error: str = "") -> None:
        now_ms = int(time.time() * 1000)
        self._store.set_last_run(job_id, now_ms)
        self._store.increment_run_count(job_id)
        self._store.add_history(job_id, {
            "timestamp": now_ms,
            "success": success,
            "durationMs": duration_ms,
            "error": error,
        })


# ─── Isolated agent runner ───

@dataclass
class CronAgentRunConfig:
    job_id: str = ""
    agent_id: str = ""
    message: str = ""
    channel: str | None = None
    timeout_ms: int = 300_000
    delivery_channel: str | None = None
    delivery_target: str | None = None


@dataclass
class CronAgentRunResult:
    success: bool = False
    reply: str = ""
    duration_ms: int = 0
    error: str | None = None
    tokens_used: int = 0


async def run_cron_agent(run_config: CronAgentRunConfig) -> CronAgentRunResult:
    """Execute an agent as part of a cron job."""
    start_ms = int(time.time() * 1000)
    result = CronAgentRunResult()

    try:
        # Import agent runner
        from ..auto_reply.reply.agent_runner_extended import run_agent_with_timeout
        
        reply = await asyncio.wait_for(
            run_agent_with_timeout(
                agent_id=run_config.agent_id,
                message=run_config.message,
                timeout_ms=run_config.timeout_ms,
            ),
            timeout=run_config.timeout_ms / 1000 + 5,
        )
        
        result.success = True
        result.reply = reply or ""
    except asyncio.TimeoutError:
        result.error = "Agent execution timed out"
    except Exception as e:
        result.error = str(e)
    
    result.duration_ms = int(time.time() * 1000) - start_ms
    return result


async def dispatch_cron_delivery(
    result: CronAgentRunResult,
    *,
    channel: str | None = None,
    target: str | None = None,
) -> bool:
    """Dispatch cron job result to a delivery channel."""
    if not result.success or not result.reply:
        return False
    if not channel or not target:
        return False

    try:
        # Route to appropriate channel adapter
        if channel == "discord":
            from ..discord import create_discord_adapter
            adapter = create_discord_adapter({})
            await adapter.send_message(target, result.reply)
            return True
        elif channel == "telegram":
            from ..telegram import create_telegram_adapter
            adapter = create_telegram_adapter({})
            await adapter.send_message(int(target), result.reply)
            return True
        elif channel == "slack":
            from ..slack import create_slack_adapter
            adapter = create_slack_adapter({})
            await adapter.send_message(target, result.reply)
            return True
    except Exception as e:
        logger.error(f"Cron delivery failed: {e}")

    return False
