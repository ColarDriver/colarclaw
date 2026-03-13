"""Context engine registry — ported from bk/src/context-engine/registry.ts.

Module-level singleton registry for context engine factories.
"""
from __future__ import annotations

from typing import Any, Callable, Awaitable

from .types import ContextEngine

ContextEngineFactory = Callable[[], ContextEngine | Awaitable[ContextEngine]]

# Module-level singleton registry
_engines: dict[str, ContextEngineFactory] = {}


def register_context_engine(engine_id: str, factory: ContextEngineFactory) -> None:
    """Register a context engine implementation under the given id."""
    _engines[engine_id] = factory


def get_context_engine_factory(engine_id: str) -> ContextEngineFactory | None:
    """Return the factory for a registered engine, or None."""
    return _engines.get(engine_id)


def list_context_engine_ids() -> list[str]:
    """List all registered engine ids."""
    return list(_engines.keys())


async def resolve_context_engine(config: dict[str, Any] | None = None) -> ContextEngine:
    """Resolve which ContextEngine to use based on plugin slot configuration.

    Resolution order:
      1. config.plugins.slots.contextEngine (explicit slot override)
      2. Default slot value ("legacy")

    Raises if the resolved engine id has no registered factory.
    """
    slot_value = None
    if config:
        slots = config.get("plugins", {}).get("slots", {})
        slot_value = slots.get("contextEngine")

    engine_id = slot_value.strip() if isinstance(slot_value, str) and slot_value.strip() else "legacy"

    factory = _engines.get(engine_id)
    if not factory:
        available = ", ".join(list_context_engine_ids()) or "(none)"
        raise RuntimeError(
            f'Context engine "{engine_id}" is not registered. '
            f"Available engines: {available}"
        )

    result = factory()
    # Support both sync and async factories
    if hasattr(result, "__await__"):
        return await result  # type: ignore[misc]
    return result  # type: ignore[return-value]
