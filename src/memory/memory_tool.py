from __future__ import annotations

import json

from ..core.config import Settings
from .search_manager import get_memory_search_manager


def memory_search_tool(
    args: dict[str, object],
    *,
    settings: Settings,
    runtime_config: dict[str, object],
    session_key: str | None = None,
) -> str:
    query = str(args.get("query", "")).strip()
    if not query:
        return json.dumps(
            {
                "results": [],
                "disabled": True,
                "unavailable": True,
                "error": "query is required",
            }
        )

    max_results = args.get("maxResults")
    min_score = args.get("minScore")
    if max_results is not None:
        try:
            max_results = int(max_results)
        except Exception:
            max_results = None
    if min_score is not None:
        try:
            min_score = float(min_score)
        except Exception:
            min_score = None

    resolved = get_memory_search_manager(settings=settings, runtime_config=runtime_config)
    if resolved.manager is None:
        return json.dumps(
            {
                "results": [],
                "disabled": True,
                "unavailable": True,
                "error": resolved.error or "memory search unavailable",
            }
        )

    try:
        results = resolved.manager.search(
            query,
            max_results=max_results,
            min_score=min_score,
            session_key=session_key,
        )
        status = resolved.manager.status()
        return json.dumps(
            {
                "results": [
                    {
                        "path": item.path,
                        "startLine": item.start_line,
                        "endLine": item.end_line,
                        "score": item.score,
                        "snippet": item.snippet,
                        "source": item.source,
                        "citation": item.citation,
                    }
                    for item in results
                ],
                "provider": status.provider,
                "model": status.model,
                "fallback": status.fallback,
                "backend": status.backend,
            }
        )
    except Exception as err:
        return json.dumps(
            {
                "results": [],
                "disabled": True,
                "unavailable": True,
                "error": str(err),
            }
        )


def memory_get_tool(
    args: dict[str, object],
    *,
    settings: Settings,
    runtime_config: dict[str, object],
) -> str:
    rel_path = str(args.get("path", "")).strip()
    if not rel_path:
        return json.dumps({"path": "", "text": "", "disabled": True, "error": "path is required"})

    from_line = args.get("from")
    lines = args.get("lines")
    if from_line is not None:
        try:
            from_line = int(from_line)
        except Exception:
            from_line = None
    if lines is not None:
        try:
            lines = int(lines)
        except Exception:
            lines = None

    resolved = get_memory_search_manager(settings=settings, runtime_config=runtime_config)
    if resolved.manager is None:
        return json.dumps({"path": rel_path, "text": "", "disabled": True, "error": resolved.error})

    try:
        text, path = resolved.manager.read_file(rel_path=rel_path, from_line=from_line, lines=lines)
        return json.dumps({"path": path, "text": text})
    except Exception as err:
        return json.dumps({"path": rel_path, "text": "", "disabled": True, "error": str(err)})
