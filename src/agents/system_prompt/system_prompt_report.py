"""System prompt report — ported from bk/src/agents/system-prompt-report.ts.

Builds a structured report of what goes into a system prompt.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillBlockEntry:
    name: str
    block_chars: int


@dataclass
class ToolEntry:
    name: str
    summary_chars: int = 0
    schema_chars: int = 0
    properties_count: int | None = None


@dataclass
class SystemPromptReport:
    source: str = ""
    generated_at: float = 0
    session_id: str | None = None
    session_key: str | None = None
    provider: str | None = None
    model: str | None = None
    workspace_dir: str | None = None
    bootstrap_max_chars: int = 0
    bootstrap_total_max_chars: int | None = None
    system_prompt_chars: int = 0
    project_context_chars: int = 0
    non_project_context_chars: int = 0
    skills_prompt_chars: int = 0
    skills_entries: list[SkillBlockEntry] = field(default_factory=list)
    tool_list_chars: int = 0
    tool_schema_chars: int = 0
    tool_entries: list[ToolEntry] = field(default_factory=list)


def _extract_between(text: str, start_marker: str, end_marker: str) -> tuple[str, bool]:
    start = text.find(start_marker)
    if start == -1:
        return "", False
    end = text.find(end_marker, start + len(start_marker))
    if end == -1:
        return text[start:], True
    return text[start:end], True


def _parse_skill_blocks(skills_prompt: str) -> list[SkillBlockEntry]:
    prompt = skills_prompt.strip()
    if not prompt:
        return []
    blocks = re.findall(r"<skill>[\s\S]*?</skill>", prompt, re.IGNORECASE)
    entries = []
    for block in blocks:
        name_match = re.search(r"<name>\s*([^<]+?)\s*</name>", block, re.IGNORECASE)
        name = name_match.group(1).strip() if name_match else "(unknown)"
        entries.append(SkillBlockEntry(name=name, block_chars=len(block)))
    return [e for e in entries if e.block_chars > 0]


def _build_tool_entries(tools: list[dict[str, Any]]) -> list[ToolEntry]:
    entries = []
    for tool in tools:
        name = tool.get("name", "")
        summary = (tool.get("description", "") or tool.get("label", "")).strip()
        try:
            schema_chars = len(json.dumps(tool.get("parameters", {})))
        except Exception:
            schema_chars = 0
        props = tool.get("parameters", {})
        if isinstance(props, dict) and isinstance(props.get("properties"), dict):
            properties_count = len(props["properties"])
        else:
            properties_count = None
        entries.append(ToolEntry(
            name=name, summary_chars=len(summary),
            schema_chars=schema_chars, properties_count=properties_count,
        ))
    return entries


def build_system_prompt_report(
    source: str,
    generated_at: float,
    system_prompt: str,
    skills_prompt: str = "",
    tools: list[dict[str, Any]] | None = None,
    bootstrap_max_chars: int = 0,
    **kwargs: Any,
) -> SystemPromptReport:
    """Build a structured system prompt report."""
    prompt = system_prompt.strip()
    project_context, _ = _extract_between(prompt, "\n# Project Context\n", "\n## Silent Replies\n")
    project_context_chars = len(project_context)

    skills_entries = _parse_skill_blocks(skills_prompt)
    tool_entries = _build_tool_entries(tools or [])
    tool_schema_chars = sum(t.schema_chars for t in tool_entries)

    return SystemPromptReport(
        source=source,
        generated_at=generated_at,
        session_id=kwargs.get("session_id"),
        session_key=kwargs.get("session_key"),
        provider=kwargs.get("provider"),
        model=kwargs.get("model"),
        workspace_dir=kwargs.get("workspace_dir"),
        bootstrap_max_chars=bootstrap_max_chars,
        bootstrap_total_max_chars=kwargs.get("bootstrap_total_max_chars"),
        system_prompt_chars=len(prompt),
        project_context_chars=project_context_chars,
        non_project_context_chars=max(0, len(prompt) - project_context_chars),
        skills_prompt_chars=len(skills_prompt),
        skills_entries=skills_entries,
        tool_schema_chars=tool_schema_chars,
        tool_entries=tool_entries,
    )
