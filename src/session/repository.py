from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .models import MessageModel, SessionModel


def _utc_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


@dataclass(frozen=True)
class SessionRecord:
    id: str
    title: str
    created_at_ms: int
    updated_at_ms: int


@dataclass(frozen=True)
class MessageRecord:
    id: str
    session_id: str
    role: str
    text: str
    created_at_ms: int


class SessionRepository(Protocol):
    async def create_session(self, title: str) -> SessionRecord: ...
    async def list_sessions(self) -> list[SessionRecord]: ...
    async def get_session(self, session_id: str) -> SessionRecord | None: ...
    async def append_message(self, session_id: str, role: str, text: str) -> MessageRecord: ...
    async def list_messages(self, session_id: str) -> list[MessageRecord]: ...


class SqlSessionRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_session(self, title: str) -> SessionRecord:
        async with self._session_factory() as db:
            row = SessionModel(title=title)
            db.add(row)
            await db.commit()
            await db.refresh(row)
            return SessionRecord(row.id, row.title, row.created_at_ms, row.updated_at_ms)

    async def list_sessions(self) -> list[SessionRecord]:
        async with self._session_factory() as db:
            rows = (await db.execute(select(SessionModel).order_by(SessionModel.updated_at_ms.desc()))).scalars().all()
            return [SessionRecord(row.id, row.title, row.created_at_ms, row.updated_at_ms) for row in rows]

    async def get_session(self, session_id: str) -> SessionRecord | None:
        async with self._session_factory() as db:
            row = await db.get(SessionModel, session_id)
            if row is None:
                return None
            return SessionRecord(row.id, row.title, row.created_at_ms, row.updated_at_ms)

    async def append_message(self, session_id: str, role: str, text: str) -> MessageRecord:
        async with self._session_factory() as db:
            message = MessageModel(session_id=session_id, role=role, text=text)
            db.add(message)
            session_row = await db.get(SessionModel, session_id)
            if session_row is not None:
                session_row.updated_at_ms = _utc_ms()
            await db.commit()
            await db.refresh(message)
            return MessageRecord(message.id, message.session_id, message.role, message.text, message.created_at_ms)

    async def list_messages(self, session_id: str) -> list[MessageRecord]:
        async with self._session_factory() as db:
            rows = (
                await db.execute(
                    select(MessageModel)
                    .where(MessageModel.session_id == session_id)
                    .order_by(MessageModel.created_at_ms.asc())
                )
            ).scalars().all()
            return [MessageRecord(row.id, row.session_id, row.role, row.text, row.created_at_ms) for row in rows]


class InMemorySessionRepository:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionRecord] = {}
        self._messages: dict[str, list[MessageRecord]] = {}

    async def create_session(self, title: str) -> SessionRecord:
        session_id = f"s_{uuid.uuid4().hex}"
        now = _utc_ms()
        record = SessionRecord(session_id, title, now, now)
        self._sessions[session_id] = record
        self._messages.setdefault(session_id, [])
        return record

    async def list_sessions(self) -> list[SessionRecord]:
        return sorted(self._sessions.values(), key=lambda item: item.updated_at_ms, reverse=True)

    async def get_session(self, session_id: str) -> SessionRecord | None:
        return self._sessions.get(session_id)

    async def append_message(self, session_id: str, role: str, text: str) -> MessageRecord:
        now = _utc_ms()
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionRecord(session_id, "Imported Session", now, now)
        msg = MessageRecord(f"m_{uuid.uuid4().hex}", session_id, role, text, now)
        self._messages.setdefault(session_id, []).append(msg)
        original = self._sessions[session_id]
        self._sessions[session_id] = SessionRecord(original.id, original.title, original.created_at_ms, now)
        return msg

    async def list_messages(self, session_id: str) -> list[MessageRecord]:
        return list(self._messages.get(session_id, []))
