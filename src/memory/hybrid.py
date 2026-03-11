from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HybridVectorResult:
    id: str
    path: str
    start_line: int
    end_line: int
    source: str
    snippet: str
    vector_score: float


@dataclass(frozen=True)
class HybridKeywordResult:
    id: str
    path: str
    start_line: int
    end_line: int
    source: str
    snippet: str
    text_score: float


def build_fts_query(raw: str) -> str | None:
    import re

    tokens = [token.strip() for token in re.findall(r"[\w]+", raw, flags=re.UNICODE) if token.strip()]
    if not tokens:
        return None
    quoted = [f'"{token.replace(chr(34), "")}"' for token in tokens]
    return ' AND '.join(quoted)


def bm25_rank_to_score(rank: float) -> float:
    if rank != rank:  # NaN
        return 1.0 / (1.0 + 999.0)
    if rank < 0:
        relevance = -rank
        return relevance / (1.0 + relevance)
    return 1.0 / (1.0 + rank)


def merge_hybrid_results(
    *,
    vector: list[HybridVectorResult],
    keyword: list[HybridKeywordResult],
    vector_weight: float,
    text_weight: float,
) -> list[dict[str, object]]:
    by_id: dict[str, dict[str, object]] = {}

    for item in vector:
        by_id[item.id] = {
            'path': item.path,
            'start_line': item.start_line,
            'end_line': item.end_line,
            'source': item.source,
            'snippet': item.snippet,
            'vector_score': item.vector_score,
            'text_score': 0.0,
        }

    for item in keyword:
        existing = by_id.get(item.id)
        if existing is None:
            by_id[item.id] = {
                'path': item.path,
                'start_line': item.start_line,
                'end_line': item.end_line,
                'source': item.source,
                'snippet': item.snippet,
                'vector_score': 0.0,
                'text_score': item.text_score,
            }
        else:
            existing['text_score'] = item.text_score
            if item.snippet:
                existing['snippet'] = item.snippet

    merged: list[dict[str, object]] = []
    for entry in by_id.values():
        vector_score = float(entry['vector_score'])
        text_score = float(entry['text_score'])
        score = (vector_weight * vector_score) + (text_weight * text_score)
        merged.append(
            {
                'path': str(entry['path']),
                'start_line': int(entry['start_line']),
                'end_line': int(entry['end_line']),
                'score': score,
                'snippet': str(entry['snippet']),
                'source': str(entry['source']),
            }
        )

    merged.sort(key=lambda item: float(item['score']), reverse=True)
    return merged
