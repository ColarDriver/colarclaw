"""Agent runner — system prompt builder for embedded agent runs.

Ported from openclaw/src/agents/pi-embedded-runner/system-prompt.ts

Wraps the lower-level build_agent_system_prompt() with tool/skill
resolution so callers don't have to assemble everything manually.
"""
from __future__ import annotations

from ..system_prompt import (
    ContextFile,
    RuntimeInfo,
    build_agent_system_prompt,
    PromptMode,
    ThinkLevel,
    ReasoningLevel,
)


def build_embedded_system_prompt(
    *,
    workspace_dir: str,
    tool_names: list[str],
    skills_prompt: str = "",
    context_files: list[ContextFile] | None = None,
    prompt_mode: PromptMode = "full",
    extra_system_prompt: str = "",
    runtime_info: RuntimeInfo | None = None,
    default_think_level: ThinkLevel = "off",
    reasoning_level: ReasoningLevel = "off",
    heartbeat_prompt: str = "",
    user_timezone: str = "",
    docs_path: str = "",
    workspace_notes: list[str] | None = None,
    owner_numbers: list[str] | None = None,
    owner_display: str = "raw",
    owner_display_secret: str = "",
    memory_citations_mode: str = "on",
    acp_enabled: bool = True,
) -> str:
    """Build the full system prompt for an embedded agent run.

    Mirrors openclaw's buildEmbeddedSystemPrompt() — resolves tool names
    and skill prompt, then delegates to the generic prompt builder.
    """
    return build_agent_system_prompt(
        workspace_dir=workspace_dir,
        prompt_mode=prompt_mode,
        tool_names=tool_names,
        extra_system_prompt=extra_system_prompt,
        owner_numbers=owner_numbers,
        skills_prompt=skills_prompt,
        heartbeat_prompt=heartbeat_prompt,
        context_files=context_files,
        runtime_info=runtime_info,
        default_think_level=default_think_level,
        reasoning_level=reasoning_level,
        user_timezone=user_timezone,
        docs_path=docs_path,
        workspace_notes=workspace_notes,
        memory_citations_mode=memory_citations_mode,
        acp_enabled=acp_enabled,
    )
