from __future__ import annotations

from pydantic import BaseModel, Field


class MemoryRuntimeUpdate(BaseModel):
    enabled: bool | None = None
    backend: str | None = None
    sources: list[str] | None = None
    extraPaths: list[str] | None = None
    sessionMemory: bool | None = None
    provider: str | None = None
    model: str | None = None
    fallback: str | None = None
    storePath: str | None = None
    vectorEnabled: bool | None = None
    chunkTokens: int | None = None
    chunkOverlap: int | None = None
    syncOnSessionStart: bool | None = None
    syncOnSearch: bool | None = None
    syncWatch: bool | None = None
    syncWatchDebounceMs: int | None = None
    syncIntervalMinutes: int | None = None
    syncSessionDeltaBytes: int | None = None
    syncSessionDeltaMessages: int | None = None
    maxResults: int | None = None
    minScore: float | None = None
    hybridEnabled: bool | None = None
    hybridVectorWeight: float | None = None
    hybridTextWeight: float | None = None
    hybridCandidateMultiplier: int | None = None
    hybridMmrEnabled: bool | None = None
    hybridMmrLambda: float | None = None
    hybridTemporalDecayEnabled: bool | None = None
    hybridTemporalDecayHalfLifeDays: float | None = None
    cacheEnabled: bool | None = None
    cacheMaxEntries: int | None = None
    qmdCommand: str | None = None
    qmdTimeoutMs: int | None = None
    qmdMaxInjectedChars: int | None = None


class SettingsView(BaseModel):
    defaultModel: str
    fallbackModels: list[str] = Field(default_factory=list)
    toolAllowlist: list[str] = Field(default_factory=list)
    toolDenylist: list[str] = Field(default_factory=list)
    maxToolCallsPerRun: int = 4
    maxSameToolRepeat: int = 3
    maxToolCallsPerMinute: int = 60
    modelRegistry: list[str] = Field(default_factory=list)
    mcpServers: list[str] = Field(default_factory=list)
    skillsEnabled: list[str] = Field(default_factory=list)


class UpdateSettingsRequest(BaseModel):
    defaultModel: str | None = None
    fallbackModels: list[str] | None = None
    toolAllowlist: list[str] | None = None
    toolDenylist: list[str] | None = None
    maxToolCallsPerRun: int | None = None
    maxSameToolRepeat: int | None = None
    maxToolCallsPerMinute: int | None = None
    modelRegistry: list[str] | None = None
    mcpServers: list[str] | None = None
    skillsEnabled: list[str] | None = None
    memory: MemoryRuntimeUpdate | None = None
