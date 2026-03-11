from __future__ import annotations

from pydantic import BaseModel, Field


class ModelItem(BaseModel):
    key: str
    provider: str
    id: str
    name: str
    reasoning: bool = False
    contextWindow: int | None = None


class McpServerItem(BaseModel):
    name: str
    command: str
    enabled: bool = True


class SkillItem(BaseModel):
    key: str
    name: str
    description: str


class UpdateRuntimeConfigRequest(BaseModel):
    modelRegistry: list[str] | None = None
    mcpServers: list[str] | None = None
    skillsEnabled: list[str] | None = None
    memory: dict[str, object] | None = None


class RuntimeConfigView(BaseModel):
    modelRegistry: list[ModelItem] = Field(default_factory=list)
    mcpServers: list[McpServerItem] = Field(default_factory=list)
    skillsEnabled: list[str] = Field(default_factory=list)
    skillsAvailable: list[SkillItem] = Field(default_factory=list)
    memory: dict[str, object] = Field(default_factory=dict)
