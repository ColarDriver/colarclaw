"""Context engine initialization — ported from bk/src/context-engine/init.ts.

Ensures built-in context engines are registered exactly once.
"""
from __future__ import annotations

from .legacy import register_legacy_context_engine

_initialized = False


def ensure_context_engines_initialized() -> None:
    """Ensure all built-in context engines are registered.

    The legacy engine is always registered as a safe fallback so that
    resolve_context_engine() can resolve the default "legacy" slot
    without callers needing manual registration.
    """
    global _initialized
    if _initialized:
        return
    _initialized = True
    register_legacy_context_engine()
