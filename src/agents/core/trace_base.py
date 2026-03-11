"""Trace base — ported from bk/src/agents/trace-base.ts.

Base trace types for agent execution tracing.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AgentTraceBase:
    run_id: str | None = None
    session_id: str | None = None
    session_key: str | None = None
    provider: str | None = None
    model_id: str | None = None
    model_api: str | None = None
    workspace_dir: str | None = None


def build_agent_trace_base(params: AgentTraceBase) -> AgentTraceBase:
    return AgentTraceBase(
        run_id=params.run_id,
        session_id=params.session_id,
        session_key=params.session_key,
        provider=params.provider,
        model_id=params.model_id,
        model_api=params.model_api,
        workspace_dir=params.workspace_dir,
    )
