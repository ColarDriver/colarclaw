from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from ..observability.audit import AuditLogger
from .policy import ToolPolicyConfig, ToolPolicyPipeline, ToolPolicyRunState, ToolRateLimiter
from .registry import ToolRegistry


@dataclass(frozen=True)
class ToolCallResult:
    name: str
    result: str


class ToolRuntime:
    def __init__(
        self,
        *,
        registry: ToolRegistry,
        allowlist: tuple[str, ...],
        audit_logger: AuditLogger,
        timeout_seconds: float = 8.0,
        denylist: tuple[str, ...] = (),
        max_calls_per_run: int = 4,
        max_same_tool_repeat: int = 3,
        max_calls_per_minute: int = 60,
    ) -> None:
        self._registry = registry
        self._audit = audit_logger
        self._timeout_seconds = timeout_seconds
        self._run_states: dict[str, ToolPolicyRunState] = {}
        self._max_calls_per_minute = max_calls_per_minute
        self._rate_limiter = ToolRateLimiter(max_calls_per_minute=max_calls_per_minute)
        self._policy = ToolPolicyPipeline(
            ToolPolicyConfig(
                allowlist=allowlist,
                denylist=denylist,
                max_calls_per_run=max_calls_per_run,
                max_same_tool_repeat=max_same_tool_repeat,
                max_calls_per_minute=max_calls_per_minute,
            )
        )

    async def execute(self, *, run_id: str, tool_name: str, args: dict[str, Any]) -> ToolCallResult:
        run_state = self._run_states.setdefault(run_id, ToolPolicyRunState())
        self._policy.pre_check(
            run_state=run_state,
            tool_name=tool_name,
            args=args,
            rate_limiter=self._rate_limiter,
        )

        definition = self._registry.get(tool_name)
        if definition is None:
            raise KeyError(f"tool '{tool_name}' is not registered")

        result = await asyncio.wait_for(definition.runner(args), timeout=self._timeout_seconds)
        self._policy.post_record(run_state=run_state, tool_name=tool_name)
        self._audit.tool_call(run_id=run_id, tool_name=tool_name, args=args, result=result)
        return ToolCallResult(name=tool_name, result=result)

    def update_policy(
        self,
        *,
        allowlist: tuple[str, ...],
        denylist: tuple[str, ...],
        max_calls_per_run: int,
        max_same_tool_repeat: int,
        max_calls_per_minute: int,
    ) -> None:
        self._policy = ToolPolicyPipeline(
            ToolPolicyConfig(
                allowlist=allowlist,
                denylist=denylist,
                max_calls_per_run=max_calls_per_run,
                max_same_tool_repeat=max_same_tool_repeat,
                max_calls_per_minute=max_calls_per_minute,
            )
        )
        if self._max_calls_per_minute != max_calls_per_minute:
            self._max_calls_per_minute = max_calls_per_minute
            self._rate_limiter = ToolRateLimiter(max_calls_per_minute=max_calls_per_minute)

    def reset_run_state(self, run_id: str) -> None:
        self._run_states.pop(run_id, None)
