from __future__ import annotations

from dataclasses import dataclass
import json
import math
import subprocess
from typing import Callable

from .types import (
    MemoryEmbeddingProbeResult,
    MemoryProviderStatus,
    MemorySearchResult,
    MemorySyncProgressUpdate,
)


@dataclass(frozen=True)
class QmdConfig:
    command: str
    timeout_ms: int
    max_results: int
    min_score: float
    max_injected_chars: int = 12_000


class QmdMemoryManager:
    def __init__(self, config: QmdConfig) -> None:
        self._config = config

    def warm_session(self, session_key: str | None = None) -> None:
        _ = session_key

    def _run_qmd(self, args: list[str], payload: dict[str, object]) -> str:
        proc = subprocess.run(
            args,
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=max(1, self._config.timeout_ms // 1000),
            check=False,
        )
        if proc.returncode != 0:
            stderr = proc.stderr.strip()
            raise RuntimeError(stderr or f"qmd command failed with exit code {proc.returncode}")
        return proc.stdout.strip()

    def _normalize_score(self, raw_score: object) -> float:
        try:
            score = float(raw_score)
        except Exception:
            return 0.0
        if math.isnan(score) or math.isinf(score):
            return 0.0
        if score < 0:
            relevance = -score
            return relevance / (1.0 + relevance)
        if score > 1.0:
            return score / (1.0 + score)
        return score

    def _extract_rows(self, parsed: object) -> list[dict[str, object]]:
        if isinstance(parsed, dict):
            if isinstance(parsed.get("results"), list):
                return [row for row in parsed["results"] if isinstance(row, dict)]
            if isinstance(parsed.get("rows"), list):
                return [row for row in parsed["rows"] if isinstance(row, dict)]
            if isinstance(parsed.get("items"), list):
                return [row for row in parsed["items"] if isinstance(row, dict)]
            if isinstance(parsed.get("data"), list):
                return [row for row in parsed["data"] if isinstance(row, dict)]
            return []
        if isinstance(parsed, list):
            return [row for row in parsed if isinstance(row, dict)]
        return []

    def _clamp_injected_chars(self, rows: list[MemorySearchResult]) -> list[MemorySearchResult]:
        budget = self._config.max_injected_chars
        if budget <= 0:
            return rows

        out: list[MemorySearchResult] = []
        remaining = budget
        for row in rows:
            if remaining <= 0:
                break
            snippet = row.snippet or ""
            if len(snippet) <= remaining:
                out.append(row)
                remaining -= len(snippet)
            else:
                out.append(
                    MemorySearchResult(
                        path=row.path,
                        start_line=row.start_line,
                        end_line=row.end_line,
                        score=row.score,
                        snippet=snippet[:remaining],
                        source=row.source,
                        citation=row.citation,
                    )
                )
                break
        return out

    def search(
        self,
        query: str,
        *,
        max_results: int | None = None,
        min_score: float | None = None,
        session_key: str | None = None,
    ) -> list[MemorySearchResult]:
        if not query.strip():
            return []

        effective_max = max_results if isinstance(max_results, int) and max_results > 0 else self._config.max_results
        effective_min = float(min_score) if isinstance(min_score, (int, float)) else self._config.min_score

        payload = {
            "query": query,
            "maxResults": effective_max,
            "minScore": effective_min,
            "sessionKey": session_key,
        }

        raw = self._run_qmd([self._config.command], payload)
        if not raw:
            return []

        parsed = json.loads(raw)
        rows = self._extract_rows(parsed)
        out: list[MemorySearchResult] = []
        for item in rows:
            score = self._normalize_score(item.get("score", 0.0))
            if score < effective_min:
                continue
            path = str(item.get("path", item.get("file", "")))
            start_line = int(item.get("startLine", item.get("start_line", item.get("line", 1))))
            end_line = int(item.get("endLine", item.get("end_line", start_line)))
            snippet = str(item.get("snippet", item.get("text", "")))
            source = str(item.get("source", "memory"))
            citation = item.get("citation")
            if citation is None and path:
                citation = (
                    f"{path}#L{start_line}" if start_line == end_line else f"{path}#L{start_line}-L{end_line}"
                )
            out.append(
                MemorySearchResult(
                    path=path,
                    start_line=start_line,
                    end_line=end_line,
                    score=score,
                    snippet=snippet,
                    source=source if source in {"memory", "sessions"} else "memory",
                    citation=str(citation) if citation is not None else None,
                )
            )
            if len(out) >= effective_max:
                break

        return self._clamp_injected_chars(out)

    def read_file(
        self,
        *,
        rel_path: str,
        from_line: int | None = None,
        lines: int | None = None,
    ) -> tuple[str, str]:
        payload = {
            "path": rel_path,
            "from": from_line,
            "lines": lines,
        }
        raw = self._run_qmd([self._config.command, "--read"], payload)
        parsed = json.loads(raw or "{}")
        text = str(parsed.get("text", ""))
        path = str(parsed.get("path", rel_path))
        return (text, path)

    def status(self) -> MemoryProviderStatus:
        return MemoryProviderStatus(
            backend="qmd",
            provider="qmd",
            model="qmd",
            custom={
                "command": self._config.command,
                "maxInjectedChars": self._config.max_injected_chars,
            },
        )

    def sync(
        self,
        *,
        reason: str | None = None,
        force: bool = False,
        progress: Callable[[MemorySyncProgressUpdate], None] | None = None,
    ) -> None:
        _ = progress
        payload = {
            "reason": reason,
            "force": force,
        }
        self._run_qmd([self._config.command, "--sync"], payload)

    def probe_embedding_availability(self) -> MemoryEmbeddingProbeResult:
        return MemoryEmbeddingProbeResult(ok=True)

    def probe_vector_availability(self) -> bool:
        return True

    def close(self) -> None:
        return
