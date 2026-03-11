"""Pi embedded runner run params — ported from bk/src/agents/pi-embedded-runner/run/params.ts."""
from __future__ import annotations

from typing import Any

from .run_types import RunParams


def build_run_params(
    session_id: str,
    message: str,
    model: str | None = None,
    provider: str | None = None,
    **kwargs: Any,
) -> RunParams:
    return RunParams(
        session_id=session_id,
        message=message,
        model=model,
        provider=provider,
        system_prompt=kwargs.get("system_prompt"),
        tools=kwargs.get("tools"),
        max_turns=kwargs.get("max_turns", 100),
        timeout_ms=kwargs.get("timeout_ms", 600_000),
    )
