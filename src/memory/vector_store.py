from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class MemoryPoint:
    session_id: str
    text: str


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._points: list[MemoryPoint] = []

    def add(self, session_id: str, text: str) -> None:
        self._points.append(MemoryPoint(session_id=session_id, text=text))

    def search(self, query: str, *, session_id: str | None = None, limit: int = 5) -> list[str]:
        query_terms = set(query.lower().split())
        scored: list[tuple[float, MemoryPoint]] = []
        for point in self._points:
            if session_id and point.session_id != session_id:
                continue
            text_terms = set(point.text.lower().split())
            overlap = len(query_terms & text_terms)
            denom = max(1.0, math.sqrt(float(len(text_terms))))
            scored.append((overlap / denom, point))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1].text for item in scored[:limit] if item[0] > 0]
