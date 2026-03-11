from __future__ import annotations

from pydantic import BaseModel, Field


class RetrievedContextItem(BaseModel):
    path: str
    startLine: int
    endLine: int
    score: float
    snippet: str
    source: str
    citation: str | None = None


class ChatRunRequest(BaseModel):
    sessionId: str
    message: str = Field(min_length=1)
    model: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    idempotencyKey: str | None = None


class ChatRunResponse(BaseModel):
    runId: str
    sessionId: str
    text: str
    tools: list[dict[str, object]]
    retrievedContext: list[RetrievedContextItem]
    deduplicated: bool = False
