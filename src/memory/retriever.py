from __future__ import annotations

from .manager import MemoryIndexManager
from .types import MemorySearchResult


class MemoryRetriever:
    def __init__(self, manager: MemoryIndexManager) -> None:
        self._manager = manager

    def retrieve(
        self,
        *,
        session_id: str,
        query: str,
        limit: int = 4,
    ) -> list[MemorySearchResult]:
        return self._manager.search(query, session_key=session_id, max_results=limit)
