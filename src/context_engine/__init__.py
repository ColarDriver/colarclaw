"""Context engine — ported from bk/src/context-engine/.

Pluggable context management for LLM sessions: message ingestion,
context assembly, compaction, and subagent lifecycle.

Modules:
    types    — core types (ContextEngine protocol, result types)
    registry — engine registration, factory, and resolution
    legacy   — LegacyContextEngine backward-compat implementation
"""
from .types import (
    ContextEngine,
    ContextEngineInfo,
    AssembleResult,
    CompactResult,
    IngestResult,
    IngestBatchResult,
    BootstrapResult,
)
from .registry import (
    register_context_engine,
    get_context_engine_factory,
    list_context_engine_ids,
    resolve_context_engine,
    ContextEngineFactory,
)
from .legacy import LegacyContextEngine, register_legacy_context_engine
from .init import ensure_context_engines_initialized
