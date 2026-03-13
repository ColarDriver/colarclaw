"""Context engine types — ported from bk/src/context-engine/types.ts.

Core type definitions for the pluggable context engine system.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Literal


# ─── result types ───

@dataclass
class AssembleResult:
    """Result of assembling model context."""
    messages: list[dict[str, Any]] = field(default_factory=list)
    estimated_tokens: int = 0
    system_prompt_addition: str | None = None


@dataclass
class CompactResult:
    """Result of context compaction."""
    ok: bool = False
    compacted: bool = False
    reason: str | None = None
    result: CompactResultDetail | None = None


@dataclass
class CompactResultDetail:
    summary: str | None = None
    first_kept_entry_id: str | None = None
    tokens_before: int = 0
    tokens_after: int | None = None
    details: Any = None


@dataclass
class IngestResult:
    """Result of ingesting a single message."""
    ingested: bool = False


@dataclass
class IngestBatchResult:
    """Result of ingesting a batch of messages."""
    ingested_count: int = 0


@dataclass
class BootstrapResult:
    """Result of engine bootstrap."""
    bootstrapped: bool = False
    imported_messages: int | None = None
    reason: str | None = None


@dataclass
class ContextEngineInfo:
    """Engine identifier and metadata."""
    id: str = ""
    name: str = ""
    version: str | None = None
    owns_compaction: bool = False


@dataclass
class SubagentSpawnPreparation:
    """Rollback handle for subagent spawn preparation."""
    rollback: Callable[[], Any] | None = None


SubagentEndReason = Literal["deleted", "completed", "swept", "released"]


# ─── ContextEngine protocol ───

class ContextEngine(ABC):
    """Pluggable contract for context management.

    Required methods define a generic lifecycle; optional methods
    allow engines to provide additional capabilities.
    """

    @property
    @abstractmethod
    def info(self) -> ContextEngineInfo:
        """Engine identifier and metadata."""
        ...

    async def bootstrap(
        self,
        session_id: str,
        session_file: str,
    ) -> BootstrapResult:
        """Initialize engine state for a session."""
        return BootstrapResult(bootstrapped=False, reason="not implemented")

    @abstractmethod
    async def ingest(
        self,
        session_id: str,
        message: dict[str, Any],
        is_heartbeat: bool = False,
    ) -> IngestResult:
        """Ingest a single message into the engine's store."""
        ...

    async def ingest_batch(
        self,
        session_id: str,
        messages: list[dict[str, Any]],
        is_heartbeat: bool = False,
    ) -> IngestBatchResult:
        """Ingest a completed turn batch as a single unit."""
        count = 0
        for msg in messages:
            result = await self.ingest(session_id, msg, is_heartbeat)
            if result.ingested:
                count += 1
        return IngestBatchResult(ingested_count=count)

    async def after_turn(
        self,
        session_id: str,
        session_file: str,
        messages: list[dict[str, Any]],
        pre_prompt_message_count: int = 0,
        auto_compaction_summary: str | None = None,
        is_heartbeat: bool = False,
        token_budget: int | None = None,
        legacy_compaction_params: dict[str, Any] | None = None,
    ) -> None:
        """Execute optional post-turn lifecycle work."""
        pass

    @abstractmethod
    async def assemble(
        self,
        session_id: str,
        messages: list[dict[str, Any]],
        token_budget: int | None = None,
    ) -> AssembleResult:
        """Assemble model context under a token budget."""
        ...

    @abstractmethod
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
        """Compact context to reduce token usage."""
        ...

    async def prepare_subagent_spawn(
        self,
        parent_session_key: str,
        child_session_key: str,
        ttl_ms: int | None = None,
    ) -> SubagentSpawnPreparation | None:
        """Prepare context-engine-managed subagent state."""
        return None

    async def on_subagent_ended(
        self,
        child_session_key: str,
        reason: SubagentEndReason = "completed",
    ) -> None:
        """Notify that a subagent lifecycle ended."""
        pass

    async def dispose(self) -> None:
        """Dispose of any resources held by the engine."""
        pass
