"""Sub-agent management — ported from bk/src/agents/acp-spawn.ts.

Manages spawning, tracking, and lifecycle of sub-agent sessions.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("openclaw.agents.subagent")


@dataclass
class SubagentConfig:
    max_concurrent: int = 5
    timeout_ms: float = 5 * 60 * 1000  # 5 minutes
    model: str | None = None
    thinking: str | None = None  # "low" | "medium" | "high" | None


@dataclass
class SubagentContext:
    parent_session_id: str
    parent_agent_id: str
    workspace_dir: str
    config: SubagentConfig = field(default_factory=SubagentConfig)


@dataclass
class SubagentStatus:
    id: str
    session_key: str
    agent_id: str
    status: str  # "pending" | "running" | "completed" | "failed" | "cancelled"
    created_at: float
    completed_at: float | None = None
    error: str | None = None
    result: str | None = None


@dataclass
class SpawnedSubagent:
    id: str
    session_key: str
    agent_id: str
    task: asyncio.Task[Any] | None = None
    status: str = "pending"
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    result: str | None = None
    error: str | None = None


class SubagentManager:
    """Manages sub-agent spawning and lifecycle."""

    def __init__(self, config: SubagentConfig | None = None):
        self._config = config or SubagentConfig()
        self._agents: dict[str, SpawnedSubagent] = {}
        self._lock = asyncio.Lock()

    @property
    def active_count(self) -> int:
        return sum(
            1 for a in self._agents.values()
            if a.status in ("pending", "running")
        )

    def _generate_session_key(self, parent_session: str) -> str:
        short_id = uuid.uuid4().hex[:8]
        return f"subagent:{parent_session}:{short_id}"

    async def spawn(
        self,
        context: SubagentContext,
        message: str,
        execute_fn: Callable[[str, str, str], Any] | None = None,
    ) -> SubagentStatus:
        """Spawn a new sub-agent session."""
        async with self._lock:
            if self.active_count >= self._config.max_concurrent:
                raise RuntimeError(
                    f"Max concurrent sub-agents reached ({self._config.max_concurrent}). "
                    f"Wait for existing sub-agents to complete."
                )

            agent_id = uuid.uuid4().hex[:12]
            session_key = self._generate_session_key(context.parent_session_id)

            agent = SpawnedSubagent(
                id=agent_id,
                session_key=session_key,
                agent_id=agent_id,
                status="running",
            )
            self._agents[agent_id] = agent

        log.info(
            "Spawned sub-agent %s (session=%s, parent=%s)",
            agent_id, session_key, context.parent_session_id,
        )

        return SubagentStatus(
            id=agent_id,
            session_key=session_key,
            agent_id=agent_id,
            status="running",
            created_at=agent.created_at,
        )

    async def get_status(self, agent_id: str) -> SubagentStatus | None:
        agent = self._agents.get(agent_id)
        if not agent:
            return None
        return SubagentStatus(
            id=agent.id,
            session_key=agent.session_key,
            agent_id=agent.agent_id,
            status=agent.status,
            created_at=agent.created_at,
            completed_at=agent.completed_at,
            error=agent.error,
            result=agent.result,
        )

    async def complete(
        self,
        agent_id: str,
        result: str | None = None,
        error: str | None = None,
    ) -> None:
        agent = self._agents.get(agent_id)
        if not agent:
            return
        agent.status = "failed" if error else "completed"
        agent.completed_at = time.time()
        agent.result = result
        agent.error = error

    async def cancel(self, agent_id: str) -> bool:
        agent = self._agents.get(agent_id)
        if not agent or agent.status not in ("pending", "running"):
            return False
        agent.status = "cancelled"
        agent.completed_at = time.time()
        if agent.task and not agent.task.done():
            agent.task.cancel()
        return True

    async def list_agents(
        self,
        parent_session_id: str | None = None,
    ) -> list[SubagentStatus]:
        agents = list(self._agents.values())
        if parent_session_id:
            agents = [
                a for a in agents
                if a.session_key.startswith(f"subagent:{parent_session_id}:")
            ]
        return [
            SubagentStatus(
                id=a.id,
                session_key=a.session_key,
                agent_id=a.agent_id,
                status=a.status,
                created_at=a.created_at,
                completed_at=a.completed_at,
                error=a.error,
                result=a.result,
            )
            for a in agents
        ]

    async def cleanup_completed(self, max_age_ms: float = 60 * 60 * 1000) -> int:
        """Remove completed/failed sub-agents older than max_age_ms."""
        now = time.time()
        to_remove: list[str] = []
        for agent_id, agent in self._agents.items():
            if agent.status in ("completed", "failed", "cancelled"):
                age = (now - agent.created_at) * 1000
                if age > max_age_ms:
                    to_remove.append(agent_id)
        for agent_id in to_remove:
            del self._agents[agent_id]
        return len(to_remove)
