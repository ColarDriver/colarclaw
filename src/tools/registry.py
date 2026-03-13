from __future__ import annotations

from functools import partial

from ..core.config import Settings
from ..memory.memory_tool import memory_get_tool, memory_search_tool
from .builtins import tool_clock_now, tool_echo_text
from .models import ToolDefinition


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        self._tools[definition.name] = definition

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def list(self) -> list[ToolDefinition]:
        return sorted(self._tools.values(), key=lambda item: item.name)


def create_default_registry(*, settings: Settings, runtime_config: dict[str, object]) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ToolDefinition(name="clock.now", description="Return UTC timestamp", runner=tool_clock_now))
    registry.register(ToolDefinition(name="echo.text", description="Echo text input", runner=tool_echo_text))
    registry.register(
        ToolDefinition(
            name="memory.search",
            description="Search memory index and return scored snippets",
            runner=partial(memory_search_tool, settings=settings, runtime_config=runtime_config),
        )
    )
    registry.register(
        ToolDefinition(
            name="memory.get",
            description="Read selected memory file lines",
            runner=partial(memory_get_tool, settings=settings, runtime_config=runtime_config),
        )
    )
    return registry
