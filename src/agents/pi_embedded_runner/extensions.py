"""Pi embedded runner extensions — ported from bk/src/agents/pi-embedded-runner/extensions.ts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class RunnerExtension:
    name: str = ""
    on_before_run: Callable[..., Any] | None = None
    on_after_run: Callable[..., Any] | None = None
    on_tool_call: Callable[..., Any] | None = None
    on_error: Callable[..., Any] | None = None


class RunnerExtensionRegistry:
    def __init__(self):
        self._extensions: list[RunnerExtension] = []

    def register(self, ext: RunnerExtension) -> None:
        self._extensions.append(ext)

    def unregister(self, name: str) -> None:
        self._extensions = [e for e in self._extensions if e.name != name]

    @property
    def extensions(self) -> list[RunnerExtension]:
        return list(self._extensions)

    async def fire_before_run(self, context: Any) -> None:
        for ext in self._extensions:
            if ext.on_before_run:
                await ext.on_before_run(context)

    async def fire_after_run(self, context: Any, result: Any) -> None:
        for ext in self._extensions:
            if ext.on_after_run:
                await ext.on_after_run(context, result)
