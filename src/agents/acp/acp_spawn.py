"""ACP spawn — ported from bk/src/agents/acp-spawn.ts.

Parameters, context, and orchestration for spawning ACP (Asynchronous
Communication Protocol) sessions.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal

log = logging.getLogger("openclaw.agents.acp_spawn")

AcpSpawnMode = Literal["direct", "relay", "background"]


@dataclass
class AcpSpawnSandboxOptions:
    enabled: bool = False
    image: str | None = None
    mount_workspace: bool = True
    network: bool = True


@dataclass
class AcpSpawnParams:
    """Parameters for spawning an ACP session."""
    agent_id: str | None = None
    model: str | None = None
    provider: str | None = None
    message: str = ""
    system_prompt: str | None = None
    workspace_dir: str | None = None
    mode: AcpSpawnMode = "direct"
    sandbox: AcpSpawnSandboxOptions | None = None
    timeout_ms: int = 300_000  # 5 minutes
    session_key: str | None = None
    parent_session_id: str | None = None
    thread_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    tools: list[str] | None = None
    tool_profile: str | None = None


@dataclass
class AcpSpawnResult:
    """Result from spawning an ACP session."""
    session_id: str | None = None
    thread_id: str | None = None
    success: bool = False
    error: str | None = None
    output: str | None = None
    exit_code: int | None = None
    started_at: float = 0
    ended_at: float = 0
    duration_ms: float = 0


@dataclass
class AcpSpawnContext:
    """Context for an active ACP spawn."""
    params: AcpSpawnParams
    session_id: str | None = None
    started_at: float = field(default_factory=lambda: time.time() * 1000)
    cancelled: bool = False


def resolve_acp_agent_id(
    agent_id: str | None = None,
    config: Any | None = None,
) -> str:
    """Resolve the agent ID for ACP spawn."""
    if agent_id:
        return agent_id
    if config:
        default_agent = getattr(config, "default_agent_id", None)
        if default_agent:
            return default_agent
    return "default"


async def spawn_acp_direct(
    params: AcpSpawnParams,
    config: Any | None = None,
) -> AcpSpawnResult:
    """Spawn an ACP session directly."""
    started_at = time.time() * 1000
    agent_id = resolve_acp_agent_id(params.agent_id, config)

    try:
        # Create session context
        context = AcpSpawnContext(
            params=params,
            started_at=started_at,
        )

        # Attempt to initialize and run the session
        result = await _run_acp_session(context, config)
        result.started_at = started_at
        result.ended_at = time.time() * 1000
        result.duration_ms = result.ended_at - result.started_at
        return result

    except asyncio.CancelledError:
        return AcpSpawnResult(
            success=False,
            error="ACP session was cancelled",
            started_at=started_at,
            ended_at=time.time() * 1000,
        )
    except Exception as exc:
        log.error("ACP spawn failed for agent %s: %s", agent_id, exc)
        return AcpSpawnResult(
            success=False,
            error=str(exc),
            started_at=started_at,
            ended_at=time.time() * 1000,
        )


async def _run_acp_session(
    context: AcpSpawnContext,
    config: Any | None = None,
) -> AcpSpawnResult:
    """Internal: run an ACP session."""
    # Placeholder — actual session creation depends on gateway/runtime infra
    return AcpSpawnResult(
        success=True,
        output="ACP session placeholder",
    )


def prepare_thread_bindings(
    parent_session_id: str | None = None,
    thread_id: str | None = None,
) -> dict[str, str]:
    """Prepare thread binding metadata for ACP spawn."""
    bindings: dict[str, str] = {}
    if parent_session_id:
        bindings["parentSessionId"] = parent_session_id
    if thread_id:
        bindings["threadId"] = thread_id
    return bindings
