from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.config import Settings
from graph.main_graph import GraphOrchestrator
from llm.router import LlmRouter
from mcp.registry import McpRegistry, parse_mcp_servers
from memory.manager import SessionMemoryRecord
from memory.retriever import MemoryRetriever
from memory.search_manager import get_memory_search_manager
from memory.store import MemoryStore
from models.registry import ModelRegistry, parse_registered_model_entries
from observability.audit import AuditLogger
from observability.metrics import InMemoryMetrics
from session.repository import InMemorySessionRepository, SessionRepository
from session.runtime import SessionRuntimeState
from skills.catalog import SkillCatalog
from tools.middleware import ToolRuntime
from tools.registry import ToolRegistry, create_default_registry


@dataclass
class Container:
    settings: Settings
    session_repo: SessionRepository
    session_runtime: SessionRuntimeState
    memory_manager: object
    memory_store: MemoryStore
    memory_retriever: MemoryRetriever
    tool_registry: ToolRegistry
    tool_runtime: ToolRuntime
    llm_router: LlmRouter
    graph: GraphOrchestrator
    metrics: InMemoryMetrics
    model_registry: ModelRegistry
    mcp_registry: McpRegistry
    skill_catalog: SkillCatalog
    runtime_config: dict[str, object]


def build_container(settings: Settings) -> Container:
    runtime_config: dict[str, object] = {
        "defaultModel": settings.default_model,
        "fallbackModels": settings.fallback_models,
        "toolAllowlist": settings.tool_allowlist,
        "toolDenylist": (),
        "maxToolCallsPerRun": 4,
        "maxSameToolRepeat": 3,
        "maxToolCallsPerMinute": 60,
        "modelRegistry": tuple(settings.model_registry),
        "mcpServers": tuple(settings.mcp_servers),
        "skillsEnabled": settings.skills_enabled,
        "memory": {
            "enabled": settings.memory_enabled,
            "backend": settings.memory_backend,
            "sources": list(settings.memory_sources),
            "extraPaths": list(settings.memory_extra_paths),
            "sessionMemory": settings.memory_session_memory_enabled,
            "provider": settings.memory_provider,
            "model": settings.memory_model,
            "fallback": settings.memory_fallback,
            "storePath": settings.memory_store_path,
            "vectorEnabled": settings.memory_vector_enabled,
            "chunkTokens": settings.memory_chunk_tokens,
            "chunkOverlap": settings.memory_chunk_overlap,
            "syncOnSessionStart": settings.memory_sync_on_session_start,
            "syncOnSearch": settings.memory_sync_on_search,
            "syncWatch": settings.memory_sync_watch,
            "syncWatchDebounceMs": settings.memory_sync_watch_debounce_ms,
            "syncIntervalMinutes": settings.memory_sync_interval_minutes,
            "syncSessionDeltaBytes": settings.memory_sync_session_delta_bytes,
            "syncSessionDeltaMessages": settings.memory_sync_session_delta_messages,
            "maxResults": settings.memory_max_results,
            "minScore": settings.memory_min_score,
            "hybridEnabled": settings.memory_hybrid_enabled,
            "hybridVectorWeight": settings.memory_hybrid_vector_weight,
            "hybridTextWeight": settings.memory_hybrid_text_weight,
            "hybridCandidateMultiplier": settings.memory_hybrid_candidate_multiplier,
            "hybridMmrEnabled": settings.memory_hybrid_mmr_enabled,
            "hybridMmrLambda": settings.memory_hybrid_mmr_lambda,
            "hybridTemporalDecayEnabled": settings.memory_hybrid_temporal_decay_enabled,
            "hybridTemporalDecayHalfLifeDays": settings.memory_hybrid_temporal_decay_half_life_days,
            "cacheEnabled": settings.memory_cache_enabled,
            "cacheMaxEntries": settings.memory_cache_max_entries,
            "qmdCommand": settings.memory_qmd_command,
            "qmdTimeoutMs": settings.memory_qmd_timeout_ms,
            "qmdMaxInjectedChars": settings.memory_qmd_max_injected_chars,
        },
    }

    session_repo = InMemorySessionRepository()

    def _session_records() -> list[SessionMemoryRecord]:
        rows: list[SessionMemoryRecord] = []
        if hasattr(session_repo, "_messages"):
            messages_map = getattr(session_repo, "_messages", {})
            for session_id, messages in messages_map.items():
                for msg in messages:
                    rows.append(
                        SessionMemoryRecord(
                            session_id=msg.session_id,
                            role=msg.role,
                            text=msg.text,
                            created_at_ms=msg.created_at_ms,
                        )
                    )
        return rows

    resolved_manager = get_memory_search_manager(
        settings=settings,
        runtime_config=runtime_config,
        session_records_provider=_session_records,
    )
    if resolved_manager.manager is None:
        raise RuntimeError(resolved_manager.error or "failed to initialize memory manager")
    memory_manager = resolved_manager.manager

    session_runtime = SessionRuntimeState(idempotency_ttl_ms=15 * 60 * 1000)
    memory_store = MemoryStore(session_repo, memory_manager)
    memory_retriever = MemoryRetriever(memory_manager)

    tool_registry = create_default_registry(settings=settings, runtime_config=runtime_config)
    audit_logger = AuditLogger()

    model_registry_entries = tuple(settings.model_registry)
    model_registry = ModelRegistry(parse_registered_model_entries(model_registry_entries))

    mcp_registry_entries = tuple(settings.mcp_servers)
    mcp_registry = McpRegistry(parse_mcp_servers(mcp_registry_entries))

    skills_root = Path("skills")
    skill_catalog = SkillCatalog(skills_root)
    skill_catalog.reload()

    tool_runtime = ToolRuntime(
        registry=tool_registry,
        allowlist=settings.tool_allowlist,
        denylist=(),
        audit_logger=audit_logger,
        timeout_seconds=8.0,
        max_calls_per_run=4,
        max_same_tool_repeat=3,
        max_calls_per_minute=60,
    )

    llm_router = LlmRouter(
        default_model=settings.default_model,
        fallback_models=settings.fallback_models,
        model_registry=model_registry,
    )

    graph = GraphOrchestrator(
        llm_router=llm_router,
        memory_store=memory_store,
        memory_retriever=memory_retriever,
        tool_runtime=tool_runtime,
        skill_catalog=skill_catalog,
        skills_enabled=settings.skills_enabled,
    )

    return Container(
        settings=settings,
        session_repo=session_repo,
        session_runtime=session_runtime,
        memory_manager=memory_manager,
        memory_store=memory_store,
        memory_retriever=memory_retriever,
        tool_registry=tool_registry,
        tool_runtime=tool_runtime,
        llm_router=llm_router,
        graph=graph,
        metrics=InMemoryMetrics(),
        model_registry=model_registry,
        mcp_registry=mcp_registry,
        skill_catalog=skill_catalog,
        runtime_config=runtime_config,
    )
