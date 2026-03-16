from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config.io import read_config_file
from .config.paths import resolve_config_path
from .core.config import Settings
from .agents.runner import AgentRunner
from .llm.providers import canonical_provider_id
from .llm.router import LlmRouter
from .mcp.registry import McpRegistry, parse_mcp_servers
from .memory.manager import SessionMemoryRecord
from .memory.retriever import MemoryRetriever
from .memory.search_manager import get_memory_search_manager
from .memory.store import MemoryStore
from .models.registry import ModelRegistry, parse_registered_model_entries
from .observability.audit import AuditLogger
from .observability.metrics import InMemoryMetrics
from .session.repository import InMemorySessionRepository, SessionRepository
from .session.runtime import SessionRuntimeState
from .agents.skills.skills_status import SkillCatalog
from .tools.middleware import ToolRuntime
from .tools.registry import ToolRegistry, create_default_registry


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
    agent_runner: AgentRunner
    metrics: InMemoryMetrics
    model_registry: ModelRegistry
    mcp_registry: McpRegistry
    skill_catalog: SkillCatalog
    runtime_config: dict[str, object]


def _as_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _normalize_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, str):
            continue
        text = raw.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(text)
    return items


def _registry_model_key(entry: object) -> str:
    if not isinstance(entry, str):
        return ""
    value = entry.strip()
    if not value:
        return ""
    if "=" in value:
        value = value.split("=", 1)[0].strip()
    return value


def _ensure_registry_contains_models(
    model_registry: tuple[str, ...] | list[str],
    model_keys: list[str],
) -> tuple[str, ...]:
    registry = _normalize_string_list(list(model_registry))
    seen = {key for key in (_registry_model_key(item) for item in registry) if key}
    for key in model_keys:
        model_key = _as_text(key)
        if not model_key or model_key in seen:
            continue
        registry.append(model_key)
        seen.add(model_key)
    return tuple(registry)


def _normalize_provider_configs(value: object) -> dict[str, dict[str, object]]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, dict[str, object]] = {}
    for raw_provider_id, raw_entry in value.items():
        if not isinstance(raw_provider_id, str) or not isinstance(raw_entry, dict):
            continue
        provider_id = canonical_provider_id(raw_provider_id)
        if not provider_id or provider_id == "echo":
            continue
        entry: dict[str, object] = {}
        api = _as_text(raw_entry.get("api")).lower()
        if api:
            entry["api"] = api
        base_url = _as_text(raw_entry.get("baseUrl"))
        if base_url:
            entry["baseUrl"] = base_url
        api_key = _as_text(raw_entry.get("apiKey"))
        if api_key:
            entry["apiKey"] = api_key
        models = _normalize_string_list(raw_entry.get("models"))
        if models:
            entry["models"] = models
        if entry:
            normalized[provider_id] = entry
    return normalized


def _load_models_runtime_from_config() -> dict[str, object]:
    try:
        config_data = read_config_file(resolve_config_path())
    except Exception:
        return {}
    if not isinstance(config_data, dict):
        return {}

    runtime_patch: dict[str, object] = {}

    agents = config_data.get("agents")
    if isinstance(agents, dict):
        defaults = agents.get("defaults")
        if isinstance(defaults, dict):
            raw_model = defaults.get("model")
            if isinstance(raw_model, str):
                default_model = raw_model.strip()
                if default_model:
                    runtime_patch["defaultModel"] = default_model
            elif isinstance(raw_model, dict):
                primary = _as_text(raw_model.get("primary"))
                if primary:
                    runtime_patch["defaultModel"] = primary
                fallbacks = _normalize_string_list(raw_model.get("fallbacks"))
                if fallbacks:
                    runtime_patch["fallbackModels"] = tuple(fallbacks)

            fallback_models = _normalize_string_list(defaults.get("fallbackModels"))
            if fallback_models:
                runtime_patch["fallbackModels"] = tuple(fallback_models)

    models = config_data.get("models")
    if isinstance(models, dict):
        model_registry = _normalize_string_list(models.get("registry"))
        if model_registry:
            runtime_patch["modelRegistry"] = tuple(model_registry)
        runtime_patch["providerConfigs"] = _normalize_provider_configs(models.get("providers"))

    return runtime_patch


def build_container(settings: Settings) -> Container:
    runtime_config: dict[str, object] = {
        "defaultModel": settings.default_model,
        "fallbackModels": settings.fallback_models,
        "providerConfigs": {},
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
    runtime_config.update(_load_models_runtime_from_config())
    runtime_config["modelRegistry"] = _ensure_registry_contains_models(
        tuple(runtime_config.get("modelRegistry", ())),
        [
            _as_text(runtime_config.get("defaultModel")),
            *_normalize_string_list(list(runtime_config.get("fallbackModels", ()))),
        ],
    )

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

    try:
        resolved_manager = get_memory_search_manager(
            settings=settings,
            runtime_config=runtime_config,
            session_records_provider=_session_records,
        )
        if resolved_manager.manager is None:
            import logging
            logging.getLogger(__name__).warning(
                f"Memory manager init failed: {resolved_manager.error}. Running with memory disabled."
            )
            memory_manager = None
        else:
            memory_manager = resolved_manager.manager
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Memory manager init error: {e}. Running with memory disabled.")
        memory_manager = None

    session_runtime = SessionRuntimeState(idempotency_ttl_ms=15 * 60 * 1000)
    memory_store = MemoryStore(session_repo, memory_manager)
    memory_retriever = MemoryRetriever(memory_manager)

    tool_registry = create_default_registry(settings=settings, runtime_config=runtime_config)
    audit_logger = AuditLogger()

    model_registry_entries = tuple(runtime_config.get("modelRegistry", ()))
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
        default_model=str(runtime_config.get("defaultModel", settings.default_model)),
        fallback_models=tuple(runtime_config.get("fallbackModels", settings.fallback_models)),
        model_registry=model_registry,
        provider_configs=runtime_config.get("providerConfigs"),
    )

    agent_runner = AgentRunner(
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
        agent_runner=agent_runner,
        metrics=InMemoryMetrics(),
        model_registry=model_registry,
        mcp_registry=mcp_registry,
        skill_catalog=skill_catalog,
        runtime_config=runtime_config,
    )
