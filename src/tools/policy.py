from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any


@dataclass(frozen=True)
class ToolPolicyConfig:
    allowlist: tuple[str, ...]
    denylist: tuple[str, ...] = ()
    max_calls_per_run: int = 4
    max_same_tool_repeat: int = 3
    max_calls_per_minute: int = 60


@dataclass
class ToolPolicyRunState:
    total_calls: int = 0
    tool_calls: dict[str, int] | None = None

    def __post_init__(self) -> None:
        if self.tool_calls is None:
            self.tool_calls = {}


class ToolRateLimiter:
    def __init__(self, max_calls_per_minute: int) -> None:
        self._max_calls_per_minute = max_calls_per_minute
        self._bucket: list[float] = []

    def allow(self) -> bool:
        now = time.time()
        one_minute_ago = now - 60
        self._bucket = [ts for ts in self._bucket if ts >= one_minute_ago]
        if len(self._bucket) >= self._max_calls_per_minute:
            return False
        self._bucket.append(now)
        return True


class ToolPolicyPipeline:
    def __init__(self, config: ToolPolicyConfig) -> None:
        self._config = config
        self._allow = set(config.allowlist)
        self._deny = set(config.denylist)

    def pre_check(
        self,
        *,
        run_state: ToolPolicyRunState,
        tool_name: str,
        args: dict[str, Any],
        rate_limiter: ToolRateLimiter,
    ) -> None:
        _ = args
        if tool_name in self._deny:
            raise PermissionError(f"tool '{tool_name}' denied by tool_policy")
        if tool_name not in self._allow:
            raise PermissionError(f"tool '{tool_name}' not in tool_policy allowlist")
        if run_state.total_calls >= self._config.max_calls_per_run:
            raise RuntimeError("tool_policy: max_calls_per_run exceeded")
        count = run_state.tool_calls.get(tool_name, 0)
        if count >= self._config.max_same_tool_repeat:
            raise RuntimeError(f"tool_policy: loop detected for tool '{tool_name}'")
        if not rate_limiter.allow():
            raise RuntimeError("tool_policy: rate limit exceeded")

    def post_record(self, *, run_state: ToolPolicyRunState, tool_name: str) -> None:
        run_state.total_calls += 1
        run_state.tool_calls[tool_name] = run_state.tool_calls.get(tool_name, 0) + 1
