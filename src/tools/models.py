from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable


ToolRunner = Callable[[dict[str, Any]], Awaitable[str]]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    runner: ToolRunner
