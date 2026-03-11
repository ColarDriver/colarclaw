from __future__ import annotations

from dataclasses import dataclass
import json
import math
import sqlite3
import threading
from pathlib import Path
from typing import Callable, Sequence

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from memory.config import MemorySearchConfig
from memory.hybrid import (
    HybridKeywordResult,
    HybridVectorResult,
    bm25_rank_to_score,
    build_fts_query,
    merge_hybrid_results,
)
from memory.internal import (
    MemoryFileEntry,
    build_file_entry,
    build_session_entry,
    chunk_markdown,
    cosine_similarity,
    hash_text,
    is_memory_path,
    list_memory_files,
    normalize_rel_path,
    parse_embedding,
)
from memory.mmr import MmrConfig, apply_mmr_to_results
from memory.temporal_decay import TemporalDecayConfig, apply_temporal_decay
from memory.types import (
    MemoryEmbeddingProbeResult,
    MemoryProviderStatus,
    MemorySearchResult,
    MemorySyncProgressUpdate,
)

SNIPPET_MAX_CHARS = 700


def _truncate_utf16_safe(value: str, max_chars: int) -> str:
    return value if len(value) <= max_chars else value[:max_chars]


class LocalHashEmbeddingProvider:
    def __init__(self, dims: int = 256) -> None:
        self._dims = max(32, dims)

    @property
    def model(self) -> str:
        return f"openclaw-local-hash-{self._dims}"

    def embed(self, text: str) -> list[float]:
        buckets = [0.0 for _ in range(self._dims)]
        lowered = text.lower()
        token_chars: list[str] = []
        for ch in lowered:
            if ch.isalnum() or ch == "_":
                token_chars.append(ch)
                continue
            if token_chars:
                self._add_token("".join(token_chars), buckets)
                token_chars = []
        if token_chars:
            self._add_token("".join(token_chars), buckets)

        norm = math.sqrt(sum(v * v for v in buckets))
        if norm <= 0:
            return buckets
        return [v / norm for v in buckets]

    def _add_token(self, token: str, buckets: list[float]) -> None:
        digest = hash_text(token)
        idx = int(digest[:8], 16) % self._dims
        sign = -1.0 if int(digest[8:10], 16) % 2 else 1.0
        buckets[idx] += sign


@dataclass(frozen=True)
class SessionMemoryRecord:
    session_id: str
    role: str
    text: str
    created_at_ms: int


@dataclass(frozen=True)
class _SearchRowResult:
    id: str
    path: str
    start_line: int
    end_line: int
    score: float
    snippet: str
    source: str


@dataclass(frozen=True)
class _SessionSnapshot:
    bytes: int
    messages: int


IGNORED_MEMORY_WATCH_DIR_NAMES = {
    ".git",
    "node_modules",
    ".pnpm-store",
    ".venv",
    "venv",
    ".tox",
    "__pycache__",
}


class _MemoryWatchHandler(FileSystemEventHandler):
    def __init__(self, manager: "MemoryIndexManager") -> None:
        self._manager = manager

    def on_any_event(self, event: FileSystemEvent) -> None:
        self._manager._on_watchdog_event(event)


class MemoryIndexManager:
    def __init__(self, config: MemorySearchConfig) -> None:
        self._config = config
        self._workspace_dir = config.workspace_dir
        self._db_path = Path(config.store.path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA busy_timeout = 5000")

        self._embedding_provider = LocalHashEmbeddingProvider()
        self._closed = False
        self._dirty = True
        self._session_warm: set[str] = set()
        self._session_records_provider: Callable[[], Sequence[SessionMemoryRecord]] | None = None
        self._lock = threading.RLock()
        self._interval_timer: threading.Timer | None = None
        self._watch_timer: threading.Timer | None = None
        self._watch_lock = threading.RLock()
        self._watch_observer: Observer | None = None
        self._watch_roots: tuple[str, ...] = ()

        self._last_session_snapshot = _SessionSnapshot(bytes=0, messages=0)
        self._pending_session_delta_bytes = 0
        self._pending_session_delta_messages = 0

        self._ensure_schema()
        self._schedule_interval_sync_if_needed()
        self._ensure_watcher()

    def attach_session_records_provider(
        self,
        provider: Callable[[], Sequence[SessionMemoryRecord]],
    ) -> None:
        self._session_records_provider = provider
        if "sessions" in self._config.sources:
            # Provider changed; force a full session delta recomputation.
            self._last_session_snapshot = _SessionSnapshot(bytes=0, messages=0)
            self.mark_dirty()

    def warm_session(self, session_key: str | None = None) -> None:
        if not self._config.sync.on_session_start:
            return
        key = (session_key or "").strip()
        if key and key in self._session_warm:
            return
        self.sync(reason="session-start")
        if key:
            self._session_warm.add(key)

    def _ensure_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS files (
                    path TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    mtime_ms REAL NOT NULL,
                    size INTEGER NOT NULL,
                    hash TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    path TEXT NOT NULL,
                    source TEXT NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    hash TEXT NOT NULL,
                    embedding TEXT NOT NULL,
                    model TEXT NOT NULL,
                    file_hash TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS chunks_path_idx ON chunks(path);
                CREATE INDEX IF NOT EXISTS chunks_model_idx ON chunks(model);
                CREATE INDEX IF NOT EXISTS chunks_source_idx ON chunks(source);

                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    id UNINDEXED,
                    path UNINDEXED,
                    source UNINDEXED,
                    model UNINDEXED,
                    start_line UNINDEXED,
                    end_line UNINDEXED,
                    text
                );
                """
            )
            self._conn.commit()

    def _ensure_watcher(self) -> None:
        if not self._config.sync.watch:
            return
        if "memory" not in self._config.sources:
            return
        if self._watch_observer is not None:
            return

        roots = self._build_watch_roots()
        if not roots:
            return

        observer = Observer()
        handler = _MemoryWatchHandler(self)
        for root in roots:
            observer.schedule(handler, root, recursive=True)
        observer.daemon = True
        observer.start()

        self._watch_observer = observer
        self._watch_roots = tuple(roots)

    def _build_watch_roots(self) -> list[str]:
        roots: set[str] = set()
        workspace = Path(self._workspace_dir).resolve()
        roots.add(str(workspace))

        for extra in self._config.extra_paths:
            try:
                extra_path = Path(extra).resolve()
            except Exception:
                continue
            if extra_path.is_file():
                roots.add(str(extra_path.parent))
            else:
                roots.add(str(extra_path))

        return sorted(roots)

    def _is_ignored_watch_path(self, abs_path: str) -> bool:
        normalized = abs_path.replace("\\", "/").lower()
        segments = [segment for segment in normalized.split("/") if segment]
        return any(segment in IGNORED_MEMORY_WATCH_DIR_NAMES for segment in segments)

    def _is_memory_watch_candidate(self, abs_path: str) -> bool:
        if self._is_ignored_watch_path(abs_path):
            return False

        path_obj = Path(abs_path)
        if path_obj.is_dir():
            return False

        suffix = path_obj.suffix.lower()
        if suffix != ".md":
            return False

        try:
            resolved = path_obj.resolve()
            workspace = Path(self._workspace_dir).resolve()
            if resolved == (workspace / "MEMORY.md").resolve() or resolved == (workspace / "memory.md").resolve():
                return True
            memory_root = (workspace / "memory").resolve()
            if str(resolved).startswith(str(memory_root) + "/") or resolved == memory_root:
                return True

            for extra in self._config.extra_paths:
                extra_path = Path(extra).resolve()
                if extra_path.is_file():
                    if resolved == extra_path:
                        return True
                    continue
                if str(resolved).startswith(str(extra_path) + "/") or resolved == extra_path:
                    return True
        except Exception:
            return False

        return False

    def _on_watchdog_event(self, event: FileSystemEvent) -> None:
        if self._closed:
            return
        if event.is_directory:
            return
        src = str(event.src_path or "")
        dst = str(getattr(event, "dest_path", "") or "")

        if src and self._is_memory_watch_candidate(src):
            self.mark_dirty(reason="watch")
            return
        if dst and self._is_memory_watch_candidate(dst):
            self.mark_dirty(reason="watch")
            return

    def _schedule_interval_sync_if_needed(self) -> None:
        minutes = self._config.sync.interval_minutes
        if minutes <= 0:
            return

        interval = max(5.0, float(minutes) * 60.0)

        def _tick() -> None:
            try:
                if not self._closed:
                    self.sync(reason="interval")
            finally:
                if not self._closed:
                    self._interval_timer = threading.Timer(interval, _tick)
                    self._interval_timer.daemon = True
                    self._interval_timer.start()

        self._interval_timer = threading.Timer(interval, _tick)
        self._interval_timer.daemon = True
        self._interval_timer.start()

    def _schedule_watch_sync(self) -> None:
        if not self._config.sync.watch:
            return
        debounce_seconds = max(0.1, self._config.sync.watch_debounce_ms / 1000.0)
        with self._watch_lock:
            if self._watch_timer is not None:
                self._watch_timer.cancel()
            self._watch_timer = threading.Timer(debounce_seconds, self._run_watch_sync)
            self._watch_timer.daemon = True
            self._watch_timer.start()

    def _run_watch_sync(self) -> None:
        with self._watch_lock:
            self._watch_timer = None
        if self._closed:
            return
        try:
            self.sync(reason="watch")
        except Exception:
            # Best effort watcher path.
            return

    def _collect_session_rows(self) -> tuple[list[SessionMemoryRecord], _SessionSnapshot]:
        if self._session_records_provider is None:
            return ([], _SessionSnapshot(bytes=0, messages=0))

        rows = list(self._session_records_provider())
        total_bytes = 0
        for row in rows:
            total_bytes += len(row.text.encode("utf-8"))
        snapshot = _SessionSnapshot(bytes=total_bytes, messages=len(rows))
        return (rows, snapshot)

    def _update_session_dirty_from_delta(self) -> bool:
        if "sessions" not in self._config.sources:
            return False

        _, snapshot = self._collect_session_rows()

        # First observation seeds baseline only; it should not force indexing.
        if self._last_session_snapshot.bytes == 0 and self._last_session_snapshot.messages == 0:
            self._last_session_snapshot = snapshot
            return False

        delta_bytes = max(0, snapshot.bytes - self._last_session_snapshot.bytes)
        delta_messages = max(0, snapshot.messages - self._last_session_snapshot.messages)

        # Handle truncation/reset similarly to TS delta logic.
        if snapshot.bytes < self._last_session_snapshot.bytes:
            delta_bytes = snapshot.bytes
        if snapshot.messages < self._last_session_snapshot.messages:
            delta_messages = snapshot.messages

        self._pending_session_delta_bytes += delta_bytes
        self._pending_session_delta_messages += delta_messages
        self._last_session_snapshot = snapshot

        threshold_bytes = self._config.sync.sessions.delta_bytes
        threshold_messages = self._config.sync.sessions.delta_messages

        bytes_hit = (
            self._pending_session_delta_bytes > 0
            if threshold_bytes <= 0
            else self._pending_session_delta_bytes >= threshold_bytes
        )
        messages_hit = (
            self._pending_session_delta_messages > 0
            if threshold_messages <= 0
            else self._pending_session_delta_messages >= threshold_messages
        )

        if bytes_hit or messages_hit:
            if threshold_bytes > 0 and bytes_hit:
                self._pending_session_delta_bytes = max(0, self._pending_session_delta_bytes - threshold_bytes)
            elif threshold_bytes <= 0:
                self._pending_session_delta_bytes = 0

            if threshold_messages > 0 and messages_hit:
                self._pending_session_delta_messages = max(
                    0,
                    self._pending_session_delta_messages - threshold_messages,
                )
            elif threshold_messages <= 0:
                self._pending_session_delta_messages = 0

            return True

        return False

    def _collect_source_entries(self) -> list[MemoryFileEntry]:
        entries: list[MemoryFileEntry] = []

        if "memory" in self._config.sources:
            source_files = list_memory_files(self._workspace_dir, self._config.extra_paths)
            entries.extend(
                entry
                for entry in (build_file_entry(path, self._workspace_dir) for path in source_files)
                if entry is not None
            )

        if "sessions" in self._config.sources and self._session_records_provider is not None:
            by_session: dict[str, list[SessionMemoryRecord]] = {}
            for record in self._session_records_provider():
                by_session.setdefault(record.session_id, []).append(record)

            for session_id, rows in by_session.items():
                rows.sort(key=lambda item: item.created_at_ms)
                lines = [f"{row.role.capitalize()}: {row.text}" for row in rows]
                content = "\n".join(lines)
                updated_at_ms = rows[-1].created_at_ms if rows else 0
                entries.append(build_session_entry(session_id, content, updated_at_ms))

        return entries

    def sync(
        self,
        *,
        reason: str | None = None,
        force: bool = False,
        progress: Callable[[MemorySyncProgressUpdate], None] | None = None,
    ) -> None:
        if self._closed:
            return

        delta_triggered = False
        if reason in {"search", "interval", "watch", "session-start", "session-delta"}:
            delta_triggered = self._update_session_dirty_from_delta()

        if not force and not self._dirty and reason not in {"search", "interval"}:
            return
        if reason in {"search", "interval"} and not force and not self._dirty and not delta_triggered:
            return
        if reason in {"search", "interval"} and not force and not self._dirty and delta_triggered:
            self._dirty = True

        with self._lock:
            valid_entries = self._collect_source_entries()
            total = len(valid_entries)

            existing = {
                row["path"]: row["hash"]
                for row in self._conn.execute("SELECT path, hash FROM files").fetchall()
            }

            touched_paths: set[str] = set()
            completed = 0

            for entry in valid_entries:
                if progress is not None:
                    progress(MemorySyncProgressUpdate(completed=completed, total=total, label=entry.path))
                touched_paths.add(entry.path)
                if not force and existing.get(entry.path) == entry.content_hash:
                    completed += 1
                    continue
                source = "sessions" if entry.path.startswith("sessions/") else "memory"
                self._reindex_entry(entry.path, entry.content, entry.content_hash, source=source)
                self._conn.execute(
                    "INSERT INTO files(path, source, mtime_ms, size, hash) VALUES(?, ?, ?, ?, ?) "
                    "ON CONFLICT(path) DO UPDATE SET source=excluded.source, mtime_ms=excluded.mtime_ms, size=excluded.size, hash=excluded.hash",
                    (entry.path, source, entry.mtime_ms, entry.size, entry.content_hash),
                )
                completed += 1

            stale_paths = [path for path in existing.keys() if path not in touched_paths]
            for stale in stale_paths:
                self._delete_path(stale)

            self._conn.commit()
            self._dirty = False

    def _delete_path(self, rel_path: str) -> None:
        self._conn.execute("DELETE FROM files WHERE path = ?", (rel_path,))
        chunk_ids = [
            row["id"] for row in self._conn.execute("SELECT id FROM chunks WHERE path = ?", (rel_path,)).fetchall()
        ]
        self._conn.execute("DELETE FROM chunks WHERE path = ?", (rel_path,))
        for chunk_id in chunk_ids:
            self._conn.execute("DELETE FROM chunks_fts WHERE id = ?", (chunk_id,))

    def _reindex_entry(self, rel_path: str, content: str, file_hash: str, *, source: str) -> None:
        self._delete_path(rel_path)
        chunks = chunk_markdown(
            content,
            tokens=self._config.chunking.tokens,
            overlap=self._config.chunking.overlap,
        )

        model = self._embedding_provider.model
        for index, chunk in enumerate(chunks):
            chunk_id = hash_text(f"{rel_path}:{chunk.start_line}:{chunk.end_line}:{chunk.content_hash}:{index}")
            embedding = self._embedding_provider.embed(chunk.text)
            embedding_json = json.dumps(embedding)
            self._conn.execute(
                "INSERT INTO chunks(id, path, source, start_line, end_line, text, hash, embedding, model, file_hash) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    chunk_id,
                    rel_path,
                    source,
                    chunk.start_line,
                    chunk.end_line,
                    chunk.text,
                    chunk.content_hash,
                    embedding_json,
                    model,
                    file_hash,
                ),
            )
            self._conn.execute(
                "INSERT INTO chunks_fts(id, path, source, model, start_line, end_line, text) VALUES(?, ?, ?, ?, ?, ?, ?)",
                (
                    chunk_id,
                    rel_path,
                    source,
                    model,
                    chunk.start_line,
                    chunk.end_line,
                    chunk.text,
                ),
            )

    def search(
        self,
        query: str,
        *,
        max_results: int | None = None,
        min_score: float | None = None,
        session_key: str | None = None,
    ) -> list[MemorySearchResult]:
        self.warm_session(session_key)
        if self._config.sync.on_search:
            self.sync(reason="search")

        cleaned = query.strip()
        if not cleaned:
            return []

        effective_max = max_results if isinstance(max_results, int) and max_results > 0 else self._config.query.max_results
        effective_min = float(min_score) if isinstance(min_score, (float, int)) else self._config.query.min_score

        source_filter_sql = ""
        source_filter_params: list[str] = []
        if self._config.sources:
            placeholders = ", ".join("?" for _ in self._config.sources)
            source_filter_sql = f" AND source IN ({placeholders})"
            source_filter_params = list(self._config.sources)

        query_vec = self._embedding_provider.embed(cleaned)
        provider_model = self._embedding_provider.model
        candidate_limit = max(effective_max, effective_max * self._config.query.hybrid.candidate_multiplier)

        with self._lock:
            vector_rows = self._search_vector(
                query_vec=query_vec,
                provider_model=provider_model,
                limit=candidate_limit,
                source_filter_sql=source_filter_sql,
                source_filter_params=source_filter_params,
            )

            keyword_rows = self._search_keyword(
                query=cleaned,
                provider_model=provider_model,
                limit=candidate_limit,
                source_filter_sql=source_filter_sql,
                source_filter_params=source_filter_params,
            )

        if self._config.query.hybrid.enabled:
            merged = merge_hybrid_results(
                vector=[
                    HybridVectorResult(
                        id=row.id,
                        path=row.path,
                        start_line=row.start_line,
                        end_line=row.end_line,
                        source=row.source,
                        snippet=row.snippet,
                        vector_score=row.score,
                    )
                    for row in vector_rows
                ],
                keyword=[
                    HybridKeywordResult(
                        id=row.id,
                        path=row.path,
                        start_line=row.start_line,
                        end_line=row.end_line,
                        source=row.source,
                        snippet=row.snippet,
                        text_score=row.score,
                    )
                    for row in keyword_rows
                ],
                vector_weight=self._config.query.hybrid.vector_weight,
                text_weight=self._config.query.hybrid.text_weight,
            )
        elif vector_rows:
            merged = [
                {
                    "path": row.path,
                    "start_line": row.start_line,
                    "end_line": row.end_line,
                    "score": row.score,
                    "snippet": row.snippet,
                    "source": row.source,
                }
                for row in vector_rows
            ]
        else:
            merged = [
                {
                    "path": row.path,
                    "start_line": row.start_line,
                    "end_line": row.end_line,
                    "score": row.score,
                    "snippet": row.snippet,
                    "source": row.source,
                }
                for row in keyword_rows
            ]

        merged = apply_temporal_decay(
            results=merged,
            workspace_dir=self._workspace_dir,
            config=TemporalDecayConfig(
                enabled=self._config.query.hybrid.temporal_decay.enabled,
                half_life_days=self._config.query.hybrid.temporal_decay.half_life_days,
            ),
        )

        merged = apply_mmr_to_results(
            merged,
            MmrConfig(
                enabled=self._config.query.hybrid.mmr.enabled,
                lambda_value=self._config.query.hybrid.mmr.lambda_value,
            ),
        )

        output: list[MemorySearchResult] = []
        for item in merged:
            score = float(item["score"])
            if score < effective_min:
                continue
            path = str(item["path"])
            start_line = int(item["start_line"])
            end_line = int(item["end_line"])
            citation = f"{path}#L{start_line}" if start_line == end_line else f"{path}#L{start_line}-L{end_line}"
            source = "sessions" if path.startswith("sessions/") else "memory"
            output.append(
                MemorySearchResult(
                    path=path,
                    start_line=start_line,
                    end_line=end_line,
                    score=score,
                    snippet=str(item["snippet"]),
                    source=source,
                    citation=citation,
                )
            )
            if len(output) >= effective_max:
                break

        return output

    def _search_vector(
        self,
        *,
        query_vec: list[float],
        provider_model: str,
        limit: int,
        source_filter_sql: str,
        source_filter_params: list[str],
    ) -> list[_SearchRowResult]:
        if not query_vec or limit <= 0:
            return []

        rows = self._conn.execute(
            f"SELECT id, path, source, start_line, end_line, text, embedding FROM chunks WHERE model = ?{source_filter_sql}",
            [provider_model, *source_filter_params],
        ).fetchall()

        scored: list[_SearchRowResult] = []
        for row in rows:
            embedding = parse_embedding(str(row["embedding"]))
            score = cosine_similarity(query_vec, embedding)
            scored.append(
                _SearchRowResult(
                    id=str(row["id"]),
                    path=str(row["path"]),
                    start_line=int(row["start_line"]),
                    end_line=int(row["end_line"]),
                    score=score,
                    snippet=_truncate_utf16_safe(str(row["text"]), SNIPPET_MAX_CHARS),
                    source=str(row["source"]),
                )
            )

        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:limit]

    def _search_keyword(
        self,
        *,
        query: str,
        provider_model: str,
        limit: int,
        source_filter_sql: str,
        source_filter_params: list[str],
    ) -> list[_SearchRowResult]:
        if limit <= 0:
            return []
        fts_query = build_fts_query(query)
        if not fts_query:
            return []

        rows = self._conn.execute(
            f"""SELECT id, path, source, start_line, end_line, text, bm25(chunks_fts) AS rank
                FROM chunks_fts
                WHERE chunks_fts MATCH ? AND model = ?{source_filter_sql}
                ORDER BY rank ASC
                LIMIT ?""",
            [fts_query, provider_model, *source_filter_params, limit],
        ).fetchall()

        return [
            _SearchRowResult(
                id=str(row["id"]),
                path=str(row["path"]),
                start_line=int(row["start_line"]),
                end_line=int(row["end_line"]),
                score=bm25_rank_to_score(float(row["rank"])),
                snippet=_truncate_utf16_safe(str(row["text"]), SNIPPET_MAX_CHARS),
                source=str(row["source"]),
            )
            for row in rows
        ]

    def read_file(
        self,
        *,
        rel_path: str,
        from_line: int | None = None,
        lines: int | None = None,
    ) -> tuple[str, str]:
        normalized = normalize_rel_path(rel_path)
        if not normalized:
            raise ValueError("path is required")

        if normalized.startswith("sessions/") and "sessions" in self._config.sources:
            with self._lock:
                rows = self._conn.execute(
                    "SELECT text FROM chunks WHERE path = ? ORDER BY start_line ASC",
                    (normalized,),
                ).fetchall()
            if not rows:
                raise FileNotFoundError(f"session memory file not found: {normalized}")
            full = "\n".join(str(row["text"]) for row in rows)
            lines_all = full.split("\n")
            start = max(1, from_line or 1)
            end = len(lines_all) if lines is None or lines <= 0 else min(len(lines_all), start + lines - 1)
            return ("\n".join(lines_all[start - 1 : end]), normalized)

        path = Path(self._workspace_dir) / normalized
        is_allowed_extra = any(
            str(path.resolve()).startswith(str(Path(extra).resolve())) for extra in self._config.extra_paths
        )
        if not is_memory_path(normalized) and not is_allowed_extra:
            raise PermissionError("memory_get path must be inside MEMORY.md, memory/, sessions/, or configured extraPaths")
        if path.suffix.lower() != ".md":
            raise PermissionError("memory_get path must point to a markdown file")

        content = path.read_text(encoding="utf-8")
        all_lines = content.split("\n")
        start = max(1, from_line or 1)
        end = len(all_lines) if lines is None or lines <= 0 else min(len(all_lines), start + lines - 1)
        selected = all_lines[start - 1 : end]
        return ("\n".join(selected), normalized)

    def status(self) -> MemoryProviderStatus:
        with self._lock:
            files = self._conn.execute("SELECT COUNT(*) AS c FROM files").fetchone()
            chunks = self._conn.execute("SELECT COUNT(*) AS c FROM chunks").fetchone()

        return MemoryProviderStatus(
            backend="builtin",
            provider=self._config.provider,
            model=self._config.model,
            requested_provider=self._config.provider,
            files=int(files["c"]) if files else 0,
            chunks=int(chunks["c"]) if chunks else 0,
            dirty=self._dirty,
            workspace_dir=self._workspace_dir,
            db_path=str(self._db_path),
            extra_paths=list(self._config.extra_paths),
            sources=list(self._config.sources),
            vector={
                "enabled": self._config.store.vector.enabled,
                "available": self._config.store.vector.enabled,
                "dims": 256,
            },
            fts={
                "enabled": True,
                "available": True,
            },
            custom={
                "syncWatchEnabled": self._config.sync.watch,
                "pendingSessionDeltaBytes": self._pending_session_delta_bytes,
                "pendingSessionDeltaMessages": self._pending_session_delta_messages,
            },
        )

    def probe_embedding_availability(self) -> MemoryEmbeddingProbeResult:
        try:
            probe = self._embedding_provider.embed("probe")
            if not probe:
                return MemoryEmbeddingProbeResult(ok=False, error="embedding provider returned empty vector")
            return MemoryEmbeddingProbeResult(ok=True)
        except Exception as err:
            return MemoryEmbeddingProbeResult(ok=False, error=str(err))

    def probe_vector_availability(self) -> bool:
        return self._config.store.vector.enabled

    def mark_dirty(self, *, reason: str | None = None) -> None:
        self._dirty = True
        if reason == "watch":
            self._schedule_watch_sync()

    def close(self) -> None:
        self._closed = True
        if self._interval_timer is not None:
            self._interval_timer.cancel()
            self._interval_timer = None
        with self._watch_lock:
            if self._watch_timer is not None:
                self._watch_timer.cancel()
                self._watch_timer = None
        if self._watch_observer is not None:
            self._watch_observer.stop()
            self._watch_observer.join(timeout=1.0)
            self._watch_observer = None
        with self._lock:
            self._conn.close()
