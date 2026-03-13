from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ..core.config import Settings

from .types import MemorySource


def _parse_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _parse_int(value: object, default: int, *, min_value: int) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except Exception:
        return default
    return max(min_value, parsed)


def _parse_float(value: object, default: float, *, min_value: float, max_value: float) -> float:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except Exception:
        return default
    return max(min_value, min(max_value, parsed))


def _parse_csv(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(item.strip() for item in value.split(",") if item.strip())
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


@dataclass(frozen=True)
class MemoryHybridMmrConfig:
    enabled: bool = False
    lambda_value: float = 0.7


@dataclass(frozen=True)
class MemoryHybridTemporalDecayConfig:
    enabled: bool = False
    half_life_days: float = 30.0


@dataclass(frozen=True)
class MemoryHybridConfig:
    enabled: bool = True
    vector_weight: float = 0.7
    text_weight: float = 0.3
    candidate_multiplier: int = 4
    mmr: MemoryHybridMmrConfig = MemoryHybridMmrConfig()
    temporal_decay: MemoryHybridTemporalDecayConfig = MemoryHybridTemporalDecayConfig()


@dataclass(frozen=True)
class MemorySyncSessionsConfig:
    delta_bytes: int = 100_000
    delta_messages: int = 50


@dataclass(frozen=True)
class MemorySyncConfig:
    on_session_start: bool = True
    on_search: bool = True
    watch: bool = False
    watch_debounce_ms: int = 1500
    interval_minutes: int = 0
    sessions: MemorySyncSessionsConfig = MemorySyncSessionsConfig()


@dataclass(frozen=True)
class MemoryQueryConfig:
    max_results: int = 6
    min_score: float = 0.35
    hybrid: MemoryHybridConfig = MemoryHybridConfig()


@dataclass(frozen=True)
class MemoryStoreVectorConfig:
    enabled: bool = True


@dataclass(frozen=True)
class MemoryStoreConfig:
    path: str
    vector: MemoryStoreVectorConfig


@dataclass(frozen=True)
class MemoryChunkingConfig:
    tokens: int = 400
    overlap: int = 80


@dataclass(frozen=True)
class MemoryCacheConfig:
    enabled: bool = True
    max_entries: int = 10_000


@dataclass(frozen=True)
class MemorySearchConfig:
    enabled: bool
    backend: Literal["builtin", "qmd"]
    sources: tuple[MemorySource, ...]
    extra_paths: tuple[str, ...]
    provider: str
    model: str
    fallback: str
    store: MemoryStoreConfig
    chunking: MemoryChunkingConfig
    sync: MemorySyncConfig
    query: MemoryQueryConfig
    cache: MemoryCacheConfig
    workspace_dir: str


def _default_store_path(settings: Settings) -> str:
    configured = settings.memory_store_path.strip()
    if configured:
        return configured
    return str(Path(settings.workspace_dir) / '.openclaw-memory' / 'default.sqlite')


def _normalize_sources(sources: tuple[str, ...], session_memory_enabled: bool) -> tuple[MemorySource, ...]:
    normalized: list[MemorySource] = []
    for source in sources:
        lowered = source.lower()
        if lowered == 'memory' and 'memory' not in normalized:
            normalized.append('memory')
        if lowered == 'sessions' and session_memory_enabled and 'sessions' not in normalized:
            normalized.append('sessions')
    if not normalized:
        normalized.append('memory')
    return tuple(normalized)


def resolve_memory_search_config(settings: Settings, runtime_cfg: dict[str, object] | None = None) -> MemorySearchConfig:
    runtime_memory = runtime_cfg.get('memory', {}) if isinstance(runtime_cfg, dict) else {}
    if not isinstance(runtime_memory, dict):
        runtime_memory = {}

    enabled = _parse_bool(runtime_memory.get('enabled', settings.memory_enabled), settings.memory_enabled)

    backend_value = str(runtime_memory.get('backend', settings.memory_backend)).strip().lower()
    backend: Literal['builtin', 'qmd']
    if backend_value == 'qmd':
        backend = 'qmd'
    else:
        backend = 'builtin'

    session_memory_enabled = _parse_bool(
        runtime_memory.get('sessionMemory', settings.memory_session_memory_enabled),
        settings.memory_session_memory_enabled,
    )

    source_values = _parse_csv(runtime_memory.get('sources', settings.memory_sources))
    sources = _normalize_sources(source_values, session_memory_enabled)

    extra_paths = _parse_csv(runtime_memory.get('extraPaths', settings.memory_extra_paths))

    provider = str(runtime_memory.get('provider', settings.memory_provider)).strip() or 'local'
    model = str(runtime_memory.get('model', settings.memory_model)).strip() or 'openclaw-local-memory-v1'
    fallback = str(runtime_memory.get('fallback', settings.memory_fallback)).strip() or 'none'

    store = MemoryStoreConfig(
        path=(str(runtime_memory.get('storePath', _default_store_path(settings))).strip() or _default_store_path(settings)),
        vector=MemoryStoreVectorConfig(
            enabled=_parse_bool(runtime_memory.get('vectorEnabled', settings.memory_vector_enabled), settings.memory_vector_enabled)
        ),
    )

    chunking = MemoryChunkingConfig(
        tokens=_parse_int(runtime_memory.get('chunkTokens', settings.memory_chunk_tokens), settings.memory_chunk_tokens, min_value=64),
        overlap=_parse_int(runtime_memory.get('chunkOverlap', settings.memory_chunk_overlap), settings.memory_chunk_overlap, min_value=0),
    )

    sync = MemorySyncConfig(
        on_session_start=_parse_bool(runtime_memory.get('syncOnSessionStart', settings.memory_sync_on_session_start), settings.memory_sync_on_session_start),
        on_search=_parse_bool(runtime_memory.get('syncOnSearch', settings.memory_sync_on_search), settings.memory_sync_on_search),
        watch=_parse_bool(runtime_memory.get('syncWatch', settings.memory_sync_watch), settings.memory_sync_watch),
        watch_debounce_ms=_parse_int(runtime_memory.get('syncWatchDebounceMs', settings.memory_sync_watch_debounce_ms), settings.memory_sync_watch_debounce_ms, min_value=100),
        interval_minutes=_parse_int(runtime_memory.get('syncIntervalMinutes', settings.memory_sync_interval_minutes), settings.memory_sync_interval_minutes, min_value=0),
        sessions=MemorySyncSessionsConfig(
            delta_bytes=_parse_int(runtime_memory.get('syncSessionDeltaBytes', settings.memory_sync_session_delta_bytes), settings.memory_sync_session_delta_bytes, min_value=1),
            delta_messages=_parse_int(runtime_memory.get('syncSessionDeltaMessages', settings.memory_sync_session_delta_messages), settings.memory_sync_session_delta_messages, min_value=1),
        ),
    )

    hybrid = MemoryHybridConfig(
        enabled=_parse_bool(runtime_memory.get('hybridEnabled', settings.memory_hybrid_enabled), settings.memory_hybrid_enabled),
        vector_weight=_parse_float(runtime_memory.get('hybridVectorWeight', settings.memory_hybrid_vector_weight), settings.memory_hybrid_vector_weight, min_value=0.0, max_value=1.0),
        text_weight=_parse_float(runtime_memory.get('hybridTextWeight', settings.memory_hybrid_text_weight), settings.memory_hybrid_text_weight, min_value=0.0, max_value=1.0),
        candidate_multiplier=_parse_int(runtime_memory.get('hybridCandidateMultiplier', settings.memory_hybrid_candidate_multiplier), settings.memory_hybrid_candidate_multiplier, min_value=1),
        mmr=MemoryHybridMmrConfig(
            enabled=_parse_bool(runtime_memory.get('hybridMmrEnabled', settings.memory_hybrid_mmr_enabled), settings.memory_hybrid_mmr_enabled),
            lambda_value=_parse_float(runtime_memory.get('hybridMmrLambda', settings.memory_hybrid_mmr_lambda), settings.memory_hybrid_mmr_lambda, min_value=0.0, max_value=1.0),
        ),
        temporal_decay=MemoryHybridTemporalDecayConfig(
            enabled=_parse_bool(runtime_memory.get('hybridTemporalDecayEnabled', settings.memory_hybrid_temporal_decay_enabled), settings.memory_hybrid_temporal_decay_enabled),
            half_life_days=_parse_float(runtime_memory.get('hybridTemporalDecayHalfLifeDays', settings.memory_hybrid_temporal_decay_half_life_days), settings.memory_hybrid_temporal_decay_half_life_days, min_value=1.0, max_value=3650.0),
        ),
    )

    query = MemoryQueryConfig(
        max_results=_parse_int(runtime_memory.get('maxResults', settings.memory_max_results), settings.memory_max_results, min_value=1),
        min_score=_parse_float(runtime_memory.get('minScore', settings.memory_min_score), settings.memory_min_score, min_value=0.0, max_value=1.0),
        hybrid=hybrid,
    )

    cache = MemoryCacheConfig(
        enabled=_parse_bool(runtime_memory.get('cacheEnabled', settings.memory_cache_enabled), settings.memory_cache_enabled),
        max_entries=_parse_int(runtime_memory.get('cacheMaxEntries', settings.memory_cache_max_entries), settings.memory_cache_max_entries, min_value=128),
    )

    return MemorySearchConfig(
        enabled=enabled,
        backend=backend,
        sources=sources,
        extra_paths=extra_paths,
        provider=provider,
        model=model,
        fallback=fallback,
        store=store,
        chunking=chunking,
        sync=sync,
        query=query,
        cache=cache,
        workspace_dir=settings.workspace_dir,
    )
