from __future__ import annotations

from pydantic import BaseModel


class CreateSessionRequest(BaseModel):
    title: str


class SessionView(BaseModel):
    id: str
    title: str
    createdAtMs: int
    updatedAtMs: int


class MessageView(BaseModel):
    id: str
    sessionId: str
    role: str
    text: str
    createdAtMs: int


class SessionDetailView(SessionView):
    messages: list[MessageView]
