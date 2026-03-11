"""Configuration schema and validation.

Ported from bk/src/config/schema.ts and bk/src/config/defaults.ts

Defines the full OpenClaw config shape using Pydantic v2.
"""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# LLM / model config
# ---------------------------------------------------------------------------

class ModelEntry(BaseModel):
    """A single model entry in agents.defaults.models map."""
    alias: str = ""
    params: dict[str, Any] = Field(default_factory=dict)


class AgentModelConfig(BaseModel):
    primary: str = ""
    fallbacks: list[str] = Field(default_factory=list)


class AgentDefaultsConfig(BaseModel):
    model: str | AgentModelConfig = ""
    fallback_models: list[str] = Field(default_factory=list, alias="fallbackModels")
    image_model: str | AgentModelConfig = Field(default="", alias="imageModel")
    thinking_default: str = Field(default="off", alias="thinkingDefault")
    models: dict[str, ModelEntry] = Field(default_factory=dict)
    max_tool_calls_per_run: int = Field(default=4, alias="maxToolCallsPerRun")
    max_same_tool_repeat: int = Field(default=3, alias="maxSameToolRepeat")
    max_tool_calls_per_minute: int = Field(default=60, alias="maxToolCallsPerMinute")
    tool_allowlist: list[str] = Field(default_factory=list, alias="toolAllowlist")
    tool_denylist: list[str] = Field(default_factory=list, alias="toolDenylist")

    class Config:
        populate_by_name = True


class AgentsConfig(BaseModel):
    defaults: AgentDefaultsConfig = Field(default_factory=AgentDefaultsConfig)


# ---------------------------------------------------------------------------
# Memory config
# ---------------------------------------------------------------------------

class MemoryConfig(BaseModel):
    enabled: bool = True
    backend: str = "builtin"
    sources: list[str] = Field(default_factory=lambda: ["memory"])
    extra_paths: list[str] = Field(default_factory=list, alias="extraPaths")
    session_memory: bool = Field(default=False, alias="sessionMemory")
    provider: str = "local"
    model: str = "openclaw-local-memory-v1"
    store_path: str = Field(default="", alias="storePath")
    vector_enabled: bool = Field(default=True, alias="vectorEnabled")
    chunk_tokens: int = Field(default=400, alias="chunkTokens")
    chunk_overlap: int = Field(default=80, alias="chunkOverlap")
    sync_on_session_start: bool = Field(default=True, alias="syncOnSessionStart")
    sync_on_search: bool = Field(default=True, alias="syncOnSearch")
    sync_watch: bool = Field(default=False, alias="syncWatch")
    max_results: int = Field(default=6, alias="maxResults")
    min_score: float = Field(default=0.35, alias="minScore")
    hybrid_enabled: bool = Field(default=True, alias="hybridEnabled")
    hybrid_vector_weight: float = Field(default=0.7, alias="hybridVectorWeight")
    hybrid_text_weight: float = Field(default=0.3, alias="hybridTextWeight")
    cache_enabled: bool = Field(default=True, alias="cacheEnabled")
    cache_max_entries: int = Field(default=10000, alias="cacheMaxEntries")

    class Config:
        populate_by_name = True


# ---------------------------------------------------------------------------
# Hooks config
# ---------------------------------------------------------------------------

class HooksConfig(BaseModel):
    pre_send: list[str] = Field(default_factory=list, alias="preSend")
    post_send: list[str] = Field(default_factory=list, alias="postSend")

    class Config:
        populate_by_name = True


# ---------------------------------------------------------------------------
# Provider model entry
# ---------------------------------------------------------------------------

class ProviderModelEntry(BaseModel):
    id: str
    name: str = ""
    reasoning: bool = False
    context_window: int | None = Field(default=None, alias="contextWindow")

    class Config:
        populate_by_name = True


class ProviderConfig(BaseModel):
    api_key: str = Field(default="", alias="apiKey")
    base_url: str = Field(default="", alias="baseUrl")
    models: list[ProviderModelEntry] = Field(default_factory=list)

    class Config:
        populate_by_name = True


class ModelsConfig(BaseModel):
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    registry: list[str] = Field(default_factory=list)
    mcp_servers: list[str] = Field(default_factory=list, alias="mcpServers")

    class Config:
        populate_by_name = True


# ---------------------------------------------------------------------------
# Skills config
# ---------------------------------------------------------------------------

class SkillsConfig(BaseModel):
    enabled: list[str] = Field(default_factory=list)
    paths: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Top-level config
# ---------------------------------------------------------------------------

class OpenClawConfig(BaseModel):
    """Full OpenClaw configuration (partial – main AI-relevant keys)."""
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    hooks: HooksConfig = Field(default_factory=HooksConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    workspace_dir: str = Field(default=".", alias="workspaceDir")
    extra_system_prompt: str = Field(default="", alias="extraSystemPrompt")

    class Config:
        populate_by_name = True

    def get_default_model(self) -> str:
        """Get the configured primary model string."""
        raw = self.agents.defaults.model
        if isinstance(raw, AgentModelConfig):
            return raw.primary or "openai/echo-default"
        return str(raw) or "openai/echo-default"

    def get_fallback_models(self) -> list[str]:
        """Get ordered fallback model list."""
        raw = self.agents.defaults.model
        if isinstance(raw, AgentModelConfig):
            return list(raw.fallbacks)
        return list(self.agents.defaults.fallback_models)

    def get_tool_allowlist(self) -> list[str]:
        return list(self.agents.defaults.tool_allowlist)

    def get_tool_denylist(self) -> list[str]:
        return list(self.agents.defaults.tool_denylist)
