from __future__ import annotations

from memory.manager import MemoryIndexManager
from session.repository import SessionRepository


class MemoryStore:
    def __init__(self, session_repo: SessionRepository, manager: MemoryIndexManager) -> None:
        self._session_repo = session_repo
        self._manager = manager

    async def write_user_message(self, session_id: str, text: str) -> None:
        await self._session_repo.append_message(session_id, "user", text)
        self._manager.mark_dirty()

    async def write_assistant_message(self, session_id: str, text: str) -> None:
        await self._session_repo.append_message(session_id, "assistant", text)
        self._manager.mark_dirty()
