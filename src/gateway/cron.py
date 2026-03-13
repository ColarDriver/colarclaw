"""Gateway cron — ported from bk/src/gateway/server-cron.ts,
server-methods/cron.ts, protocol/schema/cron.ts.

Cron job scheduling, execution, and management for the gateway.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ─── Cron job types ───

@dataclass
class CronJob:
    """A scheduled cron job."""
    id: str = ""
    name: str = ""
    schedule: str = ""  # cron expression
    command: str = ""
    session_key: str | None = None
    agent_id: str | None = None
    enabled: bool = True
    created_at_ms: int = 0
    updated_at_ms: int = 0
    last_run_ms: int | None = None
    next_run_ms: int | None = None
    run_count: int = 0
    error_count: int = 0
    last_error: str | None = None
    max_concurrent_runs: int = 1
    timeout_ms: int = 300_000  # 5 minutes
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CronRunLogEntry:
    """Log entry for a cron job execution."""
    id: str = ""
    job_id: str = ""
    started_at_ms: int = 0
    finished_at_ms: int | None = None
    status: str = "running"  # "running" | "completed" | "failed" | "timeout"
    error: str | None = None
    result: Any = None


# ─── Cron scheduler ───

class CronScheduler:
    """Manages cron job scheduling and execution.

    Handles:
    - Parsing cron expressions
    - Computing next run times
    - Executing jobs with timeout and concurrency limits
    - Recording run history
    """

    def __init__(
        self,
        *,
        execute_fn: Callable[[CronJob], Any] | None = None,
        broadcast_fn: Callable[[str, Any], None] | None = None,
        max_concurrent_runs: int = 5,
    ) -> None:
        self._jobs: dict[str, CronJob] = {}
        self._run_history: list[CronRunLogEntry] = []
        self._execute_fn = execute_fn
        self._broadcast = broadcast_fn
        self._max_concurrent = max_concurrent_runs
        self._active_runs: int = 0
        self._scheduler_task: asyncio.Task | None = None
        self._stopped = False

    def start(self) -> None:
        """Start the cron scheduler."""
        self._stopped = False
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info(f"cron scheduler started with {len(self._jobs)} jobs")

    def stop(self) -> None:
        """Stop the cron scheduler."""
        self._stopped = True
        if self._scheduler_task:
            self._scheduler_task.cancel()
            self._scheduler_task = None
        logger.info("cron scheduler stopped")

    def add_job(self, job: CronJob) -> None:
        """Add a cron job."""
        if not job.id:
            job.id = str(uuid.uuid4())
        job.created_at_ms = int(time.time() * 1000)
        job.updated_at_ms = job.created_at_ms
        self._jobs[job.id] = job
        logger.info(f"cron job added: {job.name} ({job.schedule})")

    def update_job(self, job_id: str, updates: dict[str, Any]) -> CronJob | None:
        """Update a cron job."""
        job = self._jobs.get(job_id)
        if not job:
            return None
        for key, value in updates.items():
            if hasattr(job, key):
                setattr(job, key, value)
        job.updated_at_ms = int(time.time() * 1000)
        return job

    def remove_job(self, job_id: str) -> bool:
        """Remove a cron job."""
        if job_id in self._jobs:
            del self._jobs[job_id]
            return True
        return False

    def get_job(self, job_id: str) -> CronJob | None:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[CronJob]:
        return list(self._jobs.values())

    def get_run_history(
        self,
        job_id: str | None = None,
        *,
        limit: int = 50,
    ) -> list[CronRunLogEntry]:
        """Get run history, optionally filtered by job ID."""
        runs = self._run_history
        if job_id:
            runs = [r for r in runs if r.job_id == job_id]
        return runs[-limit:]

    async def run_job(self, job_id: str) -> CronRunLogEntry | None:
        """Manually trigger a cron job."""
        job = self._jobs.get(job_id)
        if not job:
            return None
        return await self._execute_job(job)

    async def _scheduler_loop(self) -> None:
        """Main scheduler loop — checks for due jobs every 10 seconds."""
        while not self._stopped:
            try:
                await asyncio.sleep(10)
                if self._stopped:
                    break
                now_ms = int(time.time() * 1000)
                for job in self._jobs.values():
                    if not job.enabled:
                        continue
                    if job.next_run_ms and now_ms >= job.next_run_ms:
                        if self._active_runs < self._max_concurrent:
                            asyncio.create_task(self._execute_job(job))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"cron scheduler error: {e}")

    async def _execute_job(self, job: CronJob) -> CronRunLogEntry:
        """Execute a cron job with timeout protection."""
        run = CronRunLogEntry(
            id=str(uuid.uuid4()),
            job_id=job.id,
            started_at_ms=int(time.time() * 1000),
            status="running",
        )
        self._run_history.append(run)
        self._active_runs += 1

        if self._broadcast:
            self._broadcast("cron.triggered", {
                "jobId": job.id,
                "jobName": job.name,
                "runId": run.id,
            })

        try:
            if self._execute_fn:
                result = self._execute_fn(job)
                if asyncio.iscoroutine(result):
                    result = await asyncio.wait_for(result, timeout=job.timeout_ms / 1000)
                run.result = result
            run.status = "completed"
            run.finished_at_ms = int(time.time() * 1000)
            job.run_count += 1
            job.last_run_ms = run.started_at_ms
        except asyncio.TimeoutError:
            run.status = "timeout"
            run.error = f"timeout after {job.timeout_ms}ms"
            run.finished_at_ms = int(time.time() * 1000)
            job.error_count += 1
            job.last_error = run.error
        except Exception as e:
            run.status = "failed"
            run.error = str(e)
            run.finished_at_ms = int(time.time() * 1000)
            job.error_count += 1
            job.last_error = run.error
            logger.error(f"cron job {job.name} failed: {e}")
        finally:
            self._active_runs -= 1

        if self._broadcast:
            self._broadcast("cron.completed", {
                "jobId": job.id,
                "jobName": job.name,
                "runId": run.id,
                "status": run.status,
            })

        # Cap history size
        if len(self._run_history) > 500:
            self._run_history = self._run_history[-250:]

        return run

    def load_from_config(self, cfg: dict[str, Any]) -> None:
        """Load cron jobs from configuration."""
        cron_cfg = cfg.get("cron", {}) or {}
        jobs_cfg = cron_cfg.get("jobs", [])
        if not isinstance(jobs_cfg, list):
            return

        for raw in jobs_cfg:
            if not isinstance(raw, dict):
                continue
            job = CronJob(
                id=raw.get("id", str(uuid.uuid4())),
                name=raw.get("name", ""),
                schedule=raw.get("schedule", ""),
                command=raw.get("command", ""),
                session_key=raw.get("sessionKey"),
                agent_id=raw.get("agentId"),
                enabled=raw.get("enabled", True),
                max_concurrent_runs=int(raw.get("maxConcurrentRuns", 1)),
                timeout_ms=int(raw.get("timeoutMs", 300_000)),
                metadata=raw.get("metadata", {}),
            )
            self.add_job(job)
