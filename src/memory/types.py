from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Protocol


MemorySource = Literal["memory", "sessions"]


@dataclass(frozen=True)
class MemorySearchResult:
    path: str
    start_line: int
    end_line: int
    score: float
    snippet: str
    source: MemorySource
    citation: str | None = None


@dataclass(frozen=True)
class MemoryEmbeddingProbeResult:
    ok: bool
    error: str | None = None


@dataclass(frozen=True)
class MemorySyncProgressUpdate:
    completed: int
    total: int
    label: str | None = None


@dataclass(frozen=True)
class MemoryProviderStatus:
    backend: Literal["builtin", "qmd"]
    provider: str
    model: str | None = None
    requested_provider: str | None = None
    files: int | None = None
    chunks: int | None = None
    dirty: bool | None = None
    workspace_dir: str | None = None
    db_path: str | None = None
    extra_paths: list[str] | None = None
    sources: list[MemorySource] | None = None
    fallback: dict[str, str] | None = None
    vector: dict[str, object] | None = None
    fts: dict[str, object] | None = None
    custom: dict[str, object] | None = None


class MemorySearchManager(Protocol):
    def warm_session(self, session_key: str | None = None) -> None: ...

    def search(
        self,
        query: str,
        *,
        max_results: int | None = None,
        min_score: float | None = None,
        session_key: str | None = None,
    ) -> list[MemorySearchResult]: ...

    def read_file(
        self,
        *,
        rel_path: str,
        from_line: int | None = None,
        lines: int | None = None,
    ) -> tuple[str, str]: ...

    def status(self) -> MemoryProviderStatus: ...

    def sync(
        self,
        *,
        reason: str | None = None,
        force: bool = False,
        progress: Callable[[MemorySyncProgressUpdate], None] | None = None,
    ) -> None: ...

    def probe_embedding_availability(self) -> MemoryEmbeddingProbeResult: ...

    def probe_vector_availability(self) -> bool: ...

    def close(self) -> None: ...
