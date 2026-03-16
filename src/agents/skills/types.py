"""Skill types for ColarCore — based on openclaw/src/agents/skills/types.ts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillInstallSpec:
    """A single install method (brew, node, go, uv, download)."""

    id: str = ""
    kind: str = ""  # "brew" | "node" | "go" | "uv" | "download"
    label: str = ""
    bins: list[str] = field(default_factory=list)
    os: list[str] = field(default_factory=list)
    formula: str = ""
    package: str = ""
    module: str = ""
    url: str = ""


@dataclass
class ColarCoreSkillMetadata:
    """Metadata from the ``openclaw`` key inside SKILL.md frontmatter."""

    always: bool = False
    skill_key: str = ""
    primary_env: str = ""
    emoji: str = ""
    homepage: str = ""
    os: list[str] = field(default_factory=list)
    required_bins: list[str] = field(default_factory=list)
    required_any_bins: list[str] = field(default_factory=list)
    required_env: list[str] = field(default_factory=list)
    required_config: list[str] = field(default_factory=list)
    install: list[SkillInstallSpec] = field(default_factory=list)


@dataclass
class SkillFrontmatter:
    name: str = ""
    description: str = ""
    homepage: str = ""
    enabled: bool = True
    user_invocable: bool = False
    tags: list[str] = field(default_factory=list)
    metadata: ColarCoreSkillMetadata | None = None


@dataclass
class SkillDefinition:
    name: str = ""
    description: str = ""
    path: str = ""
    content: str = ""
    source: str = "workspace"  # workspace | plugin | bundled
    frontmatter: SkillFrontmatter | None = None
    enabled: bool = True


@dataclass(frozen=True)
class SkillInstallOption:
    """A normalized install option for the UI."""

    id: str
    kind: str
    label: str
    bins: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SkillEntry:
    """A single skill entry with all parsed metadata, used by the catalog and status API."""

    key: str
    name: str
    description: str
    file_path: str
    emoji: str = ""
    homepage: str = ""
    primary_env: str = ""
    bundled: bool = False
    source: str = "local"
    required_bins: list[str] = field(default_factory=list)
    required_env: list[str] = field(default_factory=list)
    required_config: list[str] = field(default_factory=list)
    required_os: list[str] = field(default_factory=list)
    install: list[SkillInstallOption] = field(default_factory=list)
    install_specs: list[SkillInstallSpec] = field(default_factory=list)
