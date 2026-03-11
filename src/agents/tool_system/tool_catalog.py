"""Tool catalog — ported from bk/src/agents/tool-catalog.ts.

Core tool definitions, profiles, sections, and group mappings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ToolProfileId = Literal["minimal", "coding", "messaging", "full"]


@dataclass
class ToolProfilePolicy:
    allow: list[str] | None = None
    deny: list[str] | None = None


@dataclass
class CoreToolEntry:
    id: str
    label: str
    description: str


@dataclass
class CoreToolSection:
    id: str
    label: str
    tools: list[CoreToolEntry] = field(default_factory=list)


@dataclass
class _CoreToolDefinition:
    id: str
    label: str
    description: str
    section_id: str
    profiles: list[ToolProfileId]
    include_in_openclaw_group: bool = False


_CORE_TOOL_SECTION_ORDER = [
    ("fs", "Files"), ("runtime", "Runtime"), ("web", "Web"),
    ("memory", "Memory"), ("sessions", "Sessions"), ("ui", "UI"),
    ("messaging", "Messaging"), ("automation", "Automation"),
    ("nodes", "Nodes"), ("agents", "Agents"), ("media", "Media"),
]

_CORE_TOOL_DEFINITIONS: list[_CoreToolDefinition] = [
    _CoreToolDefinition("read", "read", "Read file contents", "fs", ["coding"]),
    _CoreToolDefinition("write", "write", "Create or overwrite files", "fs", ["coding"]),
    _CoreToolDefinition("edit", "edit", "Make precise edits", "fs", ["coding"]),
    _CoreToolDefinition("apply_patch", "apply_patch", "Patch files (OpenAI)", "fs", ["coding"]),
    _CoreToolDefinition("exec", "exec", "Run shell commands", "runtime", ["coding"]),
    _CoreToolDefinition("process", "process", "Manage background processes", "runtime", ["coding"]),
    _CoreToolDefinition("web_search", "web_search", "Search the web", "web", [], True),
    _CoreToolDefinition("web_fetch", "web_fetch", "Fetch web content", "web", [], True),
    _CoreToolDefinition("memory_search", "memory_search", "Semantic search", "memory", ["coding"], True),
    _CoreToolDefinition("memory_get", "memory_get", "Read memory files", "memory", ["coding"], True),
    _CoreToolDefinition("sessions_list", "sessions_list", "List sessions", "sessions", ["coding", "messaging"], True),
    _CoreToolDefinition("sessions_history", "sessions_history", "Session history", "sessions", ["coding", "messaging"], True),
    _CoreToolDefinition("sessions_send", "sessions_send", "Send to session", "sessions", ["coding", "messaging"], True),
    _CoreToolDefinition("sessions_spawn", "sessions_spawn", "Spawn sub-agent", "sessions", ["coding"], True),
    _CoreToolDefinition("subagents", "subagents", "Manage sub-agents", "sessions", ["coding"], True),
    _CoreToolDefinition("session_status", "session_status", "Session status", "sessions", ["minimal", "coding", "messaging"], True),
    _CoreToolDefinition("browser", "browser", "Control web browser", "ui", [], True),
    _CoreToolDefinition("canvas", "canvas", "Control canvases", "ui", [], True),
    _CoreToolDefinition("message", "message", "Send messages", "messaging", ["messaging"], True),
    _CoreToolDefinition("cron", "cron", "Schedule tasks", "automation", ["coding"], True),
    _CoreToolDefinition("gateway", "gateway", "Gateway control", "automation", [], True),
    _CoreToolDefinition("nodes", "nodes", "Nodes + devices", "nodes", [], True),
    _CoreToolDefinition("agents_list", "agents_list", "List agents", "agents", [], True),
    _CoreToolDefinition("image", "image", "Image understanding", "media", ["coding"], True),
    _CoreToolDefinition("tts", "tts", "Text-to-speech conversion", "media", [], True),
]

_CORE_TOOL_BY_ID = {t.id: t for t in _CORE_TOOL_DEFINITIONS}


def _list_core_tool_ids_for_profile(profile: ToolProfileId) -> list[str]:
    return [t.id for t in _CORE_TOOL_DEFINITIONS if profile in t.profiles]


CORE_TOOL_PROFILES: dict[str, ToolProfilePolicy] = {
    "minimal": ToolProfilePolicy(allow=_list_core_tool_ids_for_profile("minimal")),
    "coding": ToolProfilePolicy(allow=_list_core_tool_ids_for_profile("coding")),
    "messaging": ToolProfilePolicy(allow=_list_core_tool_ids_for_profile("messaging")),
    "full": ToolProfilePolicy(),
}


def _build_core_tool_group_map() -> dict[str, list[str]]:
    section_tool_map: dict[str, list[str]] = {}
    for tool in _CORE_TOOL_DEFINITIONS:
        group_id = f"group:{tool.section_id}"
        section_tool_map.setdefault(group_id, []).append(tool.id)
    openclaw_tools = [t.id for t in _CORE_TOOL_DEFINITIONS if t.include_in_openclaw_group]
    return {"group:openclaw": openclaw_tools, **section_tool_map}


CORE_TOOL_GROUPS = _build_core_tool_group_map()

PROFILE_OPTIONS = [
    {"id": "minimal", "label": "Minimal"},
    {"id": "coding", "label": "Coding"},
    {"id": "messaging", "label": "Messaging"},
    {"id": "full", "label": "Full"},
]


def resolve_core_tool_profile_policy(profile: str | None = None) -> ToolProfilePolicy | None:
    if not profile:
        return None
    resolved = CORE_TOOL_PROFILES.get(profile)
    if not resolved:
        return None
    if not resolved.allow and not resolved.deny:
        return None
    return ToolProfilePolicy(
        allow=list(resolved.allow) if resolved.allow else None,
        deny=list(resolved.deny) if resolved.deny else None,
    )


def list_core_tool_sections() -> list[CoreToolSection]:
    sections: list[CoreToolSection] = []
    for sec_id, sec_label in _CORE_TOOL_SECTION_ORDER:
        tools = [
            CoreToolEntry(id=t.id, label=t.label, description=t.description)
            for t in _CORE_TOOL_DEFINITIONS
            if t.section_id == sec_id
        ]
        if tools:
            sections.append(CoreToolSection(id=sec_id, label=sec_label, tools=tools))
    return sections


def resolve_core_tool_profiles(tool_id: str) -> list[ToolProfileId]:
    tool = _CORE_TOOL_BY_ID.get(tool_id)
    if not tool:
        return []
    return list(tool.profiles)


def is_known_core_tool_id(tool_id: str) -> bool:
    return tool_id in _CORE_TOOL_BY_ID
