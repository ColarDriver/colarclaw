from __future__ import annotations

from dataclasses import dataclass

from ..core.config import Settings
from .config import resolve_memory_search_config
from .manager import MemoryIndexManager
from .qmd_manager import QmdConfig, QmdMemoryManager
from .types import (
    MemoryEmbeddingProbeResult,
    MemoryProviderStatus,
    MemorySearchResult,
    MemorySyncProgressUpdate,
)


@dataclass(frozen=True)
class MemorySearchManagerResult:
    manager: "MemorySearchManagerFacade | None"
    error: str | None = None


class MemorySearchManagerFacade:
    def __init__(
        self,
        *,
        primary,
        fallback_factory,
        cache_evict: callable,
        mode: str,
    ) -> None:
        self._primary = primary
        self._fallback_factory = fallback_factory
        self._fallback = None
        self._primary_failed = False
        self._last_error: str | None = None
        self._cache_evict = cache_evict
        self._mode = mode

    def _ensure_fallback(self):
        if self._fallback is not None:
            return self._fallback
        self._fallback = self._fallback_factory()
        if hasattr(self, "_session_records_provider") and self._session_records_provider is not None and hasattr(self._fallback, "attach_session_records_provider"):
            self._fallback.attach_session_records_provider(self._session_records_provider)
        return self._fallback


    def attach_session_records_provider(self, provider) -> None:
        if hasattr(self._primary, "attach_session_records_provider"):
            self._primary.attach_session_records_provider(provider)
        self._session_records_provider = provider
        if self._fallback is not None and hasattr(self._fallback, "attach_session_records_provider"):
            self._fallback.attach_session_records_provider(provider)

    def mark_dirty(self) -> None:
        if hasattr(self._primary, "mark_dirty"):
            self._primary.mark_dirty()
        if self._fallback is not None and hasattr(self._fallback, "mark_dirty"):
            self._fallback.mark_dirty()

    def warm_session(self, session_key: str | None = None) -> None:
        if not self._primary_failed:
            try:
                self._primary.warm_session(session_key)
                return
            except Exception as err:
                self._primary_failed = True
                self._last_error = str(err)
                self._cache_evict()
        fallback = self._ensure_fallback()
        fallback.warm_session(session_key)

    def search(
        self,
        query: str,
        *,
        max_results: int | None = None,
        min_score: float | None = None,
        session_key: str | None = None,
    ) -> list[MemorySearchResult]:
        if not self._primary_failed:
            try:
                return self._primary.search(
                    query,
                    max_results=max_results,
                    min_score=min_score,
                    session_key=session_key,
                )
            except Exception as err:
                self._primary_failed = True
                self._last_error = str(err)
                self._cache_evict()

        fallback = self._ensure_fallback()
        return fallback.search(
            query,
            max_results=max_results,
            min_score=min_score,
            session_key=session_key,
        )

    def read_file(
        self,
        *,
        rel_path: str,
        from_line: int | None = None,
        lines: int | None = None,
    ) -> tuple[str, str]:
        if not self._primary_failed:
            try:
                return self._primary.read_file(rel_path=rel_path, from_line=from_line, lines=lines)
            except Exception as err:
                self._primary_failed = True
                self._last_error = str(err)
                self._cache_evict()

        fallback = self._ensure_fallback()
        return fallback.read_file(rel_path=rel_path, from_line=from_line, lines=lines)

    def status(self) -> MemoryProviderStatus:
        if not self._primary_failed:
            return self._primary.status()
        fallback = self._ensure_fallback()
        status = fallback.status()
        return MemoryProviderStatus(
            backend=status.backend,
            provider=status.provider,
            model=status.model,
            requested_provider=status.requested_provider,
            files=status.files,
            chunks=status.chunks,
            dirty=status.dirty,
            workspace_dir=status.workspace_dir,
            db_path=status.db_path,
            extra_paths=status.extra_paths,
            sources=status.sources,
            fallback={"from": self._mode, "reason": self._last_error or "unknown"},
            vector=status.vector,
            fts=status.fts,
            custom=status.custom,
        )

    def sync(
        self,
        *,
        reason: str | None = None,
        force: bool = False,
        progress: callable | None = None,
    ) -> None:
        if not self._primary_failed:
            try:
                self._primary.sync(reason=reason, force=force, progress=progress)
                return
            except Exception as err:
                self._primary_failed = True
                self._last_error = str(err)
                self._cache_evict()
        fallback = self._ensure_fallback()
        fallback.sync(reason=reason, force=force, progress=progress)

    def probe_embedding_availability(self) -> MemoryEmbeddingProbeResult:
        if not self._primary_failed:
            try:
                return self._primary.probe_embedding_availability()
            except Exception:
                pass
        return self._ensure_fallback().probe_embedding_availability()

    def probe_vector_availability(self) -> bool:
        if not self._primary_failed:
            try:
                return self._primary.probe_vector_availability()
            except Exception:
                pass
        return self._ensure_fallback().probe_vector_availability()

    def close(self) -> None:
        try:
            self._primary.close()
        finally:
            if self._fallback is not None:
                self._fallback.close()


_MANAGER_CACHE: dict[str, MemorySearchManagerFacade] = {}


def _build_builtin_manager(config) -> MemoryIndexManager:
    return MemoryIndexManager(config)


def _bind_session_provider(manager, provider) -> None:
    if provider is not None and hasattr(manager, "attach_session_records_provider"):
        manager.attach_session_records_provider(provider)


def _build_qmd_manager(settings: Settings, runtime_config: dict[str, object] | None):
    runtime_memory = runtime_config.get("memory", {}) if isinstance(runtime_config, dict) else {}
    if not isinstance(runtime_memory, dict):
        runtime_memory = {}

    command = str(runtime_memory.get("qmdCommand") or "").strip()
    if not command:
        raise RuntimeError("qmd backend selected but memory.qmdCommand is empty")

    timeout_ms = int(runtime_memory.get("qmdTimeoutMs") or 30000)
    max_results = int(runtime_memory.get("maxResults") or settings.memory_max_results)
    min_score = float(runtime_memory.get("minScore") or settings.memory_min_score)

    max_injected_chars = int(runtime_memory.get("qmdMaxInjectedChars") or settings.memory_qmd_max_injected_chars)

    qmd = QmdMemoryManager(
        QmdConfig(
            command=command,
            timeout_ms=timeout_ms,
            max_results=max_results,
            min_score=min_score,
            max_injected_chars=max_injected_chars,
        )
    )
    return qmd


def get_memory_search_manager(
    *,
    settings: Settings,
    runtime_config: dict[str, object] | None,
    agent_id: str = "default",
    session_records_provider=None,
) -> MemorySearchManagerResult:
    config = resolve_memory_search_config(settings, runtime_config)
    if not config.enabled:
        return MemorySearchManagerResult(manager=None, error="memory search disabled")

    cache_key = (
        f"{agent_id}:{config.store.path}:{config.backend}:{config.provider}:{config.model}:"
        f"{config.sources}:{config.extra_paths}:{config.sync.interval_minutes}:"
        f"{config.sync.on_search}:{config.sync.on_session_start}"
    )

    existing = _MANAGER_CACHE.get(cache_key)
    if existing is not None:
        return MemorySearchManagerResult(manager=existing)

    try:
        if config.backend == "qmd":
            primary = _build_qmd_manager(settings, runtime_config)
            mode = "qmd"
        else:
            primary = _build_builtin_manager(config)
            mode = "builtin"

        facade = MemorySearchManagerFacade(
            primary=primary,
            fallback_factory=lambda: _build_builtin_manager(config),
            cache_evict=lambda: _MANAGER_CACHE.pop(cache_key, None),
            mode=mode,
        )
        _bind_session_provider(primary, session_records_provider)
        _MANAGER_CACHE[cache_key] = facade
        return MemorySearchManagerResult(manager=facade)
    except Exception as err:
        # If qmd fails during init, hard fallback to builtin.
        if config.backend == "qmd":
            try:
                fallback = _build_builtin_manager(config)
                facade = MemorySearchManagerFacade(
                    primary=fallback,
                    fallback_factory=lambda: _build_builtin_manager(config),
                    cache_evict=lambda: _MANAGER_CACHE.pop(cache_key, None),
                    mode="qmd",
                )
                _bind_session_provider(fallback, session_records_provider)
                _MANAGER_CACHE[cache_key] = facade
                return MemorySearchManagerResult(manager=facade, error=str(err))
            except Exception as fallback_err:
                return MemorySearchManagerResult(manager=None, error=str(fallback_err))

        return MemorySearchManagerResult(manager=None, error=str(err))


def close_memory_managers() -> None:
    managers = list(_MANAGER_CACHE.values())
    _MANAGER_CACHE.clear()
    for manager in managers:
        manager.close()
