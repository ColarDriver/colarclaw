from __future__ import annotations

from dataclasses import dataclass
import os


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except Exception:
        return default


@dataclass(frozen=True)
class Settings:
    env: str
    host: str
    port: int
    api_token: str
    jwt_secret: str
    jwt_issuer: str
    jwt_audience: str
    database_url: str
    redis_url: str
    vector_backend: str
    default_model: str
    fallback_models: tuple[str, ...]
    tool_allowlist: tuple[str, ...]
    model_registry: tuple[str, ...]
    mcp_servers: tuple[str, ...]
    skills_enabled: tuple[str, ...]

    workspace_dir: str

    memory_enabled: bool
    memory_backend: str
    memory_sources: tuple[str, ...]
    memory_extra_paths: tuple[str, ...]
    memory_session_memory_enabled: bool

    memory_provider: str
    memory_model: str
    memory_fallback: str
    memory_store_path: str
    memory_vector_enabled: bool

    memory_chunk_tokens: int
    memory_chunk_overlap: int

    memory_sync_on_session_start: bool
    memory_sync_on_search: bool
    memory_sync_watch: bool
    memory_sync_watch_debounce_ms: int
    memory_sync_interval_minutes: int
    memory_sync_session_delta_bytes: int
    memory_sync_session_delta_messages: int

    memory_max_results: int
    memory_min_score: float

    memory_hybrid_enabled: bool
    memory_hybrid_vector_weight: float
    memory_hybrid_text_weight: float
    memory_hybrid_candidate_multiplier: int
    memory_hybrid_mmr_enabled: bool
    memory_hybrid_mmr_lambda: float
    memory_hybrid_temporal_decay_enabled: bool
    memory_hybrid_temporal_decay_half_life_days: float

    memory_cache_enabled: bool
    memory_cache_max_entries: int

    memory_qmd_command: str
    memory_qmd_timeout_ms: int
    memory_qmd_max_injected_chars: int


def load_settings() -> Settings:
    return Settings(
        env=os.getenv("OPENCLAW_ENV", "dev"),
        host=os.getenv("OPENCLAW_HOST", "0.0.0.0"),
        port=int(os.getenv("OPENCLAW_PORT", "8788")),
        api_token=os.getenv("OPENCLAW_API_TOKEN", "openclaw-dev-token"),
        jwt_secret=os.getenv("OPENCLAW_JWT_SECRET", "openclaw-dev-jwt-secret"),
        jwt_issuer=os.getenv("OPENCLAW_JWT_ISSUER", "openclaw"),
        jwt_audience=os.getenv("OPENCLAW_JWT_AUDIENCE", "openclaw-web"),
        database_url=os.getenv("OPENCLAW_DATABASE_URL", "sqlite+aiosqlite:///./openclaw.db"),
        redis_url=os.getenv("OPENCLAW_REDIS_URL", "redis://localhost:6379/0"),
        vector_backend=os.getenv("OPENCLAW_VECTOR_BACKEND", "memory"),
        default_model=os.getenv("OPENCLAW_DEFAULT_MODEL", "openai/echo-default"),
        fallback_models=_split_csv(
            os.getenv("OPENCLAW_FALLBACK_MODELS", "openai/echo-fallback-1,openai/echo-fallback-2")
        ),
        tool_allowlist=_split_csv(
            os.getenv("OPENCLAW_TOOL_ALLOWLIST", "clock.now,echo.text,memory.search,memory.get")
        ),
        model_registry=_split_csv(
            os.getenv(
                "OPENCLAW_MODEL_REGISTRY",
                "openai/echo-default=Echo Default,openai/echo-fallback-1=Echo Fallback 1,openai/echo-fallback-2=Echo Fallback 2",
            )
        ),
        mcp_servers=_split_csv(
            os.getenv("OPENCLAW_MCP_SERVERS", "qmd=mcporter daemon start")
        ),
        skills_enabled=_split_csv(os.getenv("OPENCLAW_SKILLS_ENABLED", "")),
        workspace_dir=os.getenv("OPENCLAW_WORKSPACE_DIR", os.getcwd()),
        memory_enabled=_env_bool("OPENCLAW_MEMORY_ENABLED", True),
        memory_backend=os.getenv("OPENCLAW_MEMORY_BACKEND", "builtin"),
        memory_sources=_split_csv(os.getenv("OPENCLAW_MEMORY_SOURCES", "memory")),
        memory_extra_paths=_split_csv(os.getenv("OPENCLAW_MEMORY_EXTRA_PATHS", "")),
        memory_session_memory_enabled=_env_bool("OPENCLAW_MEMORY_SESSION_ENABLED", False),
        memory_provider=os.getenv("OPENCLAW_MEMORY_PROVIDER", "local"),
        memory_model=os.getenv("OPENCLAW_MEMORY_MODEL", "openclaw-local-memory-v1"),
        memory_fallback=os.getenv("OPENCLAW_MEMORY_FALLBACK", "none"),
        memory_store_path=os.getenv("OPENCLAW_MEMORY_STORE_PATH", ""),
        memory_vector_enabled=_env_bool("OPENCLAW_MEMORY_VECTOR_ENABLED", True),
        memory_chunk_tokens=_env_int("OPENCLAW_MEMORY_CHUNK_TOKENS", 400),
        memory_chunk_overlap=_env_int("OPENCLAW_MEMORY_CHUNK_OVERLAP", 80),
        memory_sync_on_session_start=_env_bool("OPENCLAW_MEMORY_SYNC_ON_SESSION_START", True),
        memory_sync_on_search=_env_bool("OPENCLAW_MEMORY_SYNC_ON_SEARCH", True),
        memory_sync_watch=_env_bool("OPENCLAW_MEMORY_SYNC_WATCH", False),
        memory_sync_watch_debounce_ms=_env_int("OPENCLAW_MEMORY_SYNC_WATCH_DEBOUNCE_MS", 1500),
        memory_sync_interval_minutes=_env_int("OPENCLAW_MEMORY_SYNC_INTERVAL_MINUTES", 0),
        memory_sync_session_delta_bytes=_env_int("OPENCLAW_MEMORY_SYNC_SESSION_DELTA_BYTES", 100000),
        memory_sync_session_delta_messages=_env_int("OPENCLAW_MEMORY_SYNC_SESSION_DELTA_MESSAGES", 50),
        memory_max_results=_env_int("OPENCLAW_MEMORY_MAX_RESULTS", 6),
        memory_min_score=_env_float("OPENCLAW_MEMORY_MIN_SCORE", 0.35),
        memory_hybrid_enabled=_env_bool("OPENCLAW_MEMORY_HYBRID_ENABLED", True),
        memory_hybrid_vector_weight=_env_float("OPENCLAW_MEMORY_HYBRID_VECTOR_WEIGHT", 0.7),
        memory_hybrid_text_weight=_env_float("OPENCLAW_MEMORY_HYBRID_TEXT_WEIGHT", 0.3),
        memory_hybrid_candidate_multiplier=_env_int("OPENCLAW_MEMORY_HYBRID_CANDIDATE_MULTIPLIER", 4),
        memory_hybrid_mmr_enabled=_env_bool("OPENCLAW_MEMORY_MMR_ENABLED", False),
        memory_hybrid_mmr_lambda=_env_float("OPENCLAW_MEMORY_MMR_LAMBDA", 0.7),
        memory_hybrid_temporal_decay_enabled=_env_bool("OPENCLAW_MEMORY_TEMPORAL_DECAY_ENABLED", False),
        memory_hybrid_temporal_decay_half_life_days=_env_float("OPENCLAW_MEMORY_TEMPORAL_DECAY_HALF_LIFE_DAYS", 30.0),
        memory_cache_enabled=_env_bool("OPENCLAW_MEMORY_CACHE_ENABLED", True),
        memory_cache_max_entries=_env_int("OPENCLAW_MEMORY_CACHE_MAX_ENTRIES", 10000),
        memory_qmd_command=os.getenv("OPENCLAW_MEMORY_QMD_COMMAND", ""),
        memory_qmd_timeout_ms=_env_int("OPENCLAW_MEMORY_QMD_TIMEOUT_MS", 30000),
        memory_qmd_max_injected_chars=_env_int("OPENCLAW_MEMORY_QMD_MAX_INJECTED_CHARS", 12000),
    )
