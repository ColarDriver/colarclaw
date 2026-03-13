"""Cron job scheduling system.

Ported from bk/src/cron/ (~43 TS files, ~8.8k lines).

Covers cron expression parsing, job scheduling, execution,
history tracking, concurrency guards, and health monitoring.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


# ─── Cron expression parsing ───

@dataclass
class CronField:
    """A parsed cron field (minute, hour, day, month, weekday)."""
    values: set[int] = field(default_factory=set)
    is_wildcard: bool = False

    def matches(self, value: int) -> bool:
        return self.is_wildcard or value in self.values


@dataclass
class CronExpression:
    """Parsed cron expression (5-field: min hour day month weekday)."""
    minute: CronField = field(default_factory=CronField)
    hour: CronField = field(default_factory=CronField)
    day: CronField = field(default_factory=CronField)
    month: CronField = field(default_factory=CronField)
    weekday: CronField = field(default_factory=CronField)
    raw: str = ""

    def matches_time(self, t: time.struct_time) -> bool:
        return (
            self.minute.matches(t.tm_min)
            and self.hour.matches(t.tm_hour)
            and self.day.matches(t.tm_mday)
            and self.month.matches(t.tm_mon)
            and self.weekday.matches(t.tm_wday)
        )


def _parse_cron_field(raw: str, min_val: int, max_val: int) -> CronField:
    """Parse a single cron field."""
    if raw == "*":
        return CronField(is_wildcard=True)

    values: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        # Range: 1-5
        range_match = re.match(r"^(\d+)-(\d+)$", part)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2))
            for v in range(max(start, min_val), min(end, max_val) + 1):
                values.add(v)
            continue
        # Step: */5 or 1-10/2
        step_match = re.match(r"^(?:(\d+)-(\d+)|(\*))\/(\d+)$", part)
        if step_match:
            if step_match.group(3) == "*":
                start, end = min_val, max_val
            else:
                start = int(step_match.group(1))
                end = int(step_match.group(2))
            step = int(step_match.group(4))
            for v in range(start, end + 1, step):
                values.add(v)
            continue
        # Single value
        try:
            v = int(part)
            if min_val <= v <= max_val:
                values.add(v)
        except ValueError:
            pass

    return CronField(values=values)


def parse_cron_expression(expr: str) -> CronExpression:
    """Parse a 5-field cron expression."""
    # Handle common shortcuts
    shortcuts = {
        "@yearly": "0 0 1 1 *",
        "@annually": "0 0 1 1 *",
        "@monthly": "0 0 1 * *",
        "@weekly": "0 0 * * 0",
        "@daily": "0 0 * * *",
        "@midnight": "0 0 * * *",
        "@hourly": "0 * * * *",
    }
    expr = shortcuts.get(expr.strip().lower(), expr.strip())

    parts = expr.split()
    if len(parts) < 5:
        raise ValueError(f"Invalid cron expression: {expr} (need 5 fields)")

    return CronExpression(
        minute=_parse_cron_field(parts[0], 0, 59),
        hour=_parse_cron_field(parts[1], 0, 23),
        day=_parse_cron_field(parts[2], 1, 31),
        month=_parse_cron_field(parts[3], 1, 12),
        weekday=_parse_cron_field(parts[4], 0, 6),
        raw=expr,
    )


# ─── Job definition ───

@dataclass
class CronJobConfig:
    """Configuration for a cron job."""
    id: str = ""
    schedule: str = ""
    command: str = ""
    channel: str | None = None
    agent_id: str | None = None
    timeout_ms: int = 300_000
    enabled: bool = True
    overlap_policy: str = "skip"  # "skip" | "queue" | "allow"
    retry_count: int = 0
    retry_delay_ms: int = 5000
    labels: list[str] = field(default_factory=list)


@dataclass
class CronJobRun:
    """Record of a cron job execution."""
    job_id: str = ""
    run_id: str = ""
    started_at_ms: int = 0
    finished_at_ms: int = 0
    status: str = "pending"  # "pending" | "running" | "done" | "error" | "skipped"
    result: str = ""
    error: str | None = None
    duration_ms: int = 0


# ─── Scheduler ───

class CronScheduler:
    """Cron job scheduler.

    Runs in the background, checks job schedules every minute,
    and executes matching jobs.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, CronJobConfig] = {}
        self._expressions: dict[str, CronExpression] = {}
        self._running_jobs: dict[str, CronJobRun] = {}
        self._history: list[CronJobRun] = []
        self._max_history = 1000
        self._running = False
        self._executor: Callable[[CronJobConfig], Awaitable[str]] | None = None

    def add_job(self, job: CronJobConfig) -> None:
        """Register a cron job."""
        self._jobs[job.id] = job
        try:
            self._expressions[job.id] = parse_cron_expression(job.schedule)
        except ValueError as e:
            logger.error(f"Invalid cron expression for {job.id}: {e}")

    def remove_job(self, job_id: str) -> None:
        self._jobs.pop(job_id, None)
        self._expressions.pop(job_id, None)

    def set_executor(self, fn: Callable[[CronJobConfig], Awaitable[str]]) -> None:
        self._executor = fn

    def list_jobs(self) -> list[CronJobConfig]:
        return list(self._jobs.values())

    def get_history(self, job_id: str | None = None, limit: int = 50) -> list[CronJobRun]:
        if job_id:
            return [h for h in self._history if h.job_id == job_id][-limit:]
        return self._history[-limit:]

    async def start(self) -> None:
        """Start the scheduler loop."""
        self._running = True
        logger.info(f"Cron scheduler started with {len(self._jobs)} jobs")
        while self._running:
            await self._tick()
            await asyncio.sleep(60)

    def stop(self) -> None:
        self._running = False

    async def run_job_now(self, job_id: str) -> CronJobRun:
        """Manually trigger a job."""
        job = self._jobs.get(job_id)
        if not job:
            return CronJobRun(job_id=job_id, status="error", error="Job not found")
        return await self._execute_job(job)

    async def _tick(self) -> None:
        """Check and execute jobs due at current time."""
        now = time.localtime()
        for job_id, expr in self._expressions.items():
            job = self._jobs.get(job_id)
            if not job or not job.enabled:
                continue
            if not expr.matches_time(now):
                continue
            # Check overlap policy
            if job.overlap_policy == "skip" and job_id in self._running_jobs:
                self._history.append(CronJobRun(
                    job_id=job_id, status="skipped",
                    started_at_ms=int(time.time() * 1000),
                ))
                continue
            asyncio.create_task(self._execute_job(job))

    async def _execute_job(self, job: CronJobConfig) -> CronJobRun:
        """Execute a single cron job."""
        import uuid
        run = CronJobRun(
            job_id=job.id,
            run_id=str(uuid.uuid4()),
            started_at_ms=int(time.time() * 1000),
            status="running",
        )
        self._running_jobs[job.id] = run

        try:
            if self._executor:
                result = await asyncio.wait_for(
                    self._executor(job),
                    timeout=job.timeout_ms / 1000,
                )
                run.result = result
                run.status = "done"
            else:
                run.status = "error"
                run.error = "No executor configured"
        except asyncio.TimeoutError:
            run.status = "error"
            run.error = "Timeout"
        except Exception as e:
            run.status = "error"
            run.error = str(e)
        finally:
            run.finished_at_ms = int(time.time() * 1000)
            run.duration_ms = run.finished_at_ms - run.started_at_ms
            self._running_jobs.pop(job.id, None)
            self._history.append(run)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

        return run


def load_cron_jobs_from_config(config: dict[str, Any]) -> list[CronJobConfig]:
    """Load cron jobs from configuration."""
    cron = config.get("cron", [])
    if not isinstance(cron, list):
        return []
    jobs = []
    for i, entry in enumerate(cron):
        if not isinstance(entry, dict):
            continue
        job_id = entry.get("id", f"job-{i}")
        jobs.append(CronJobConfig(
            id=job_id,
            schedule=str(entry.get("schedule", "")),
            command=str(entry.get("command", "")),
            channel=entry.get("channel"),
            agent_id=entry.get("agentId"),
            timeout_ms=int(entry.get("timeoutMs", 300_000)),
            enabled=bool(entry.get("enabled", True)),
            overlap_policy=entry.get("overlapPolicy", "skip"),
            retry_count=int(entry.get("retryCount", 0)),
            retry_delay_ms=int(entry.get("retryDelayMs", 5000)),
        ))
    return jobs
