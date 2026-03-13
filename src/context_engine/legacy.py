"""Context engine legacy — ported from bk/src/context-engine/legacy.ts.

LegacyContextEngine: backward-compatible pass-through implementation.
"""
from __future__ import annotations

from typing import Any

from .registry import register_context_engine
from .types import (
    AssembleResult,
    CompactResult,
    CompactResultDetail,
    ContextEngine,
    ContextEngineInfo,
    IngestResult,
)


class LegacyContextEngine(ContextEngine):
    """Legacy engine wrapping existing compaction behavior.

    - ingest: no-op (SessionManager handles persistence)
    - assemble: pass-through (existing pipeline handles assembly)
    - compact: delegates to compaction runtime
    """

    @property
    def info(self) -> ContextEngineInfo:
        return ContextEngineInfo(
            id="legacy",
            name="Legacy Context Engine",
            version="1.0.0",
        )

    async def ingest(
        self,
        session_id: str,
        message: dict[str, Any],
        is_heartbeat: bool = False,
    ) -> IngestResult:
        return IngestResult(ingested=False)

    async def assemble(
        self,
        session_id: str,
        messages: list[dict[str, Any]],
        token_budget: int | None = None,
    ) -> AssembleResult:
        return AssembleResult(
            messages=messages,
            estimated_tokens=0,
        )

    async def after_turn(self, **kwargs: Any) -> None:  # type: ignore[override]
        pass

    async def compact(
        self,
        session_id: str,
        session_file: str,
        token_budget: int | None = None,
        force: bool = False,
        current_token_count: int | None = None,
        compaction_target: str = "budget",
        custom_instructions: str | None = None,
        legacy_params: dict[str, Any] | None = None,
    ) -> CompactResult:
        """Delegate compaction to external compaction runtime.

        In the full implementation this would call the compaction pipeline.
        """
        # Stub: full implementation would call compaction runtime
        return CompactResult(
            ok=True,
            compacted=False,
            reason="legacy stub — no compaction performed",
        )

    async def dispose(self) -> None:
        pass


def register_legacy_context_engine() -> None:
    """Register the legacy engine as the default."""
    register_context_engine("legacy", lambda: LegacyContextEngine())
