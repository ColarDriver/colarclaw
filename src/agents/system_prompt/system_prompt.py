"""System prompt builder.

Ported from bk/src/agents/system-prompt.ts

Builds the full agent system prompt sections including:
- Tooling section
- Safety section
- Memory/Skills sections
- Runtime info section
- Context files injection
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from typing import Literal

SILENT_REPLY_TOKEN = "[[SILENT_REPLY]]"

PromptMode = Literal["full", "minimal", "none"]
ThinkLevel = Literal["off", "minimal", "low", "medium", "high", "xhigh", "adaptive"]
ReasoningLevel = Literal["off", "on", "stream"]


@dataclass
class RuntimeInfo:
    agent_id: str = ""
    host: str = ""
    os: str = ""
    arch: str = ""
    model: str = ""
    default_model: str = ""
    shell: str = ""
    channel: str = ""
    capabilities: list[str] = field(default_factory=list)
    repo_root: str = ""


@dataclass
class ContextFile:
    path: str
    content: str


@dataclass
class SandboxInfo:
    enabled: bool = False
    container_workspace_dir: str = ""
    workspace_dir: str = ""
    workspace_access: str = ""
    agent_workspace_mount: str = ""
    browser_bridge_url: str = ""
    browser_no_vnc_url: str = ""
    host_browser_allowed: bool | None = None
    elevated_allowed: bool = False
    elevated_default_level: str = ""


# ---------------------------------------------------------------------------
# Section builders (mirror the TS helper functions)
# ---------------------------------------------------------------------------

def _build_skills_section(*, skills_prompt: str, read_tool_name: str = "read") -> list[str]:
    trimmed = skills_prompt.strip()
    if not trimmed:
        return []
    return [
        "## Skills (mandatory)",
        "Before replying: scan <available_skills> <description> entries.",
        f"- If exactly one skill clearly applies: read its SKILL.md at <location> with `{read_tool_name}`, then follow it.",
        "- If multiple could apply: choose the most specific one, then read/follow it.",
        "- If none clearly apply: do not read any SKILL.md.",
        "Constraints: never read more than one skill up front; only read after selecting.",
        "- When a skill drives external API writes, assume rate limits: prefer fewer larger writes, avoid tight one-item loops, serialize bursts when possible, and respect 429/Retry-After.",
        trimmed,
        "",
    ]


def _build_memory_section(
    *,
    is_minimal: bool,
    available_tools: set[str],
    citations_mode: str = "on",
) -> list[str]:
    if is_minimal:
        return []
    if "memory_search" not in available_tools and "memory_get" not in available_tools:
        return []
    lines = [
        "## Memory Recall",
        "Before answering anything about prior work, decisions, dates, people, preferences, or todos: run memory_search on MEMORY.md + memory/*.md; then use memory_get to pull only the needed lines. If low confidence after search, say you checked.",
    ]
    if citations_mode == "off":
        lines.append(
            "Citations are disabled: do not mention file paths or line numbers in replies unless the user explicitly asks."
        )
    else:
        lines.append("Citations: include Source: <path#line> when it helps the user verify memory snippets.")
    lines.append("")
    return lines


def _format_owner_display_id(owner_id: str, owner_display_secret: str = "") -> str:
    if owner_display_secret.strip():
        digest = hmac.new(
            owner_display_secret.encode(),
            owner_id.encode(),
            hashlib.sha256,
        ).hexdigest()
    else:
        digest = hashlib.sha256(owner_id.encode()).hexdigest()
    return digest[:12]


def _build_owner_identity_line(
    owner_numbers: list[str],
    owner_display: Literal["raw", "hash"] = "raw",
    owner_display_secret: str = "",
) -> str | None:
    normalized = [v.strip() for v in owner_numbers if v.strip()]
    if not normalized:
        return None
    if owner_display == "hash":
        display_ids = [_format_owner_display_id(o, owner_display_secret) for o in normalized]
    else:
        display_ids = normalized
    return f"Authorized senders: {', '.join(display_ids)}. These senders are allowlisted; do not assume they are the owner."


def _build_runtime_line(
    runtime_info: RuntimeInfo | None,
    runtime_channel: str = "",
    runtime_capabilities: list[str] | None = None,
    default_think_level: ThinkLevel = "off",
) -> str:
    caps = runtime_capabilities or []
    parts = []
    if runtime_info:
        if runtime_info.agent_id:
            parts.append(f"agent={runtime_info.agent_id}")
        if runtime_info.host:
            parts.append(f"host={runtime_info.host}")
        if runtime_info.repo_root:
            parts.append(f"repo={runtime_info.repo_root}")
        if runtime_info.os:
            arch_part = f" ({runtime_info.arch})" if runtime_info.arch else ""
            parts.append(f"os={runtime_info.os}{arch_part}")
        elif runtime_info.arch:
            parts.append(f"arch={runtime_info.arch}")
        if runtime_info.model:
            parts.append(f"model={runtime_info.model}")
        if runtime_info.default_model:
            parts.append(f"default_model={runtime_info.default_model}")
        if runtime_info.shell:
            parts.append(f"shell={runtime_info.shell}")
    if runtime_channel:
        parts.append(f"channel={runtime_channel}")
        caps_str = ",".join(caps) if caps else "none"
        parts.append(f"capabilities={caps_str}")
    parts.append(f"thinking={default_think_level}")
    return "Runtime: " + " | ".join(parts)


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_agent_system_prompt(
    *,
    workspace_dir: str,
    prompt_mode: PromptMode = "full",
    tool_names: list[str] | None = None,
    tool_summaries: dict[str, str] | None = None,
    extra_system_prompt: str = "",
    owner_numbers: list[str] | None = None,
    owner_display: Literal["raw", "hash"] = "raw",
    owner_display_secret: str = "",
    skills_prompt: str = "",
    heartbeat_prompt: str = "",
    context_files: list[ContextFile] | None = None,
    runtime_info: RuntimeInfo | None = None,
    sandbox_info: SandboxInfo | None = None,
    default_think_level: ThinkLevel = "off",
    reasoning_level: ReasoningLevel = "off",
    user_timezone: str = "",
    docs_path: str = "",
    workspace_notes: list[str] | None = None,
    memory_citations_mode: str = "on",
    acp_enabled: bool = True,
    bootstrap_truncation_warning_lines: list[str] | None = None,
) -> str:
    if prompt_mode == "none":
        return "You are a personal assistant running inside OpenClaw."

    is_minimal = prompt_mode == "minimal"
    available_tools = set((t.strip().lower() for t in (tool_names or [])) if tool_names else [])
    runtime_channel = (runtime_info.channel.strip().lower() if runtime_info and runtime_info.channel else "")
    runtime_capabilities = (runtime_info.capabilities if runtime_info else [])
    caps_lower = {c.lower() for c in runtime_capabilities}
    inline_buttons_enabled = "inlinebuttons" in caps_lower
    sandboxed = sandbox_info and sandbox_info.enabled
    acp_spawn_runtime_enabled = acp_enabled and not sandboxed
    has_sessions_spawn = "sessions_spawn" in available_tools

    # --- Core tool summaries ---
    core_summaries: dict[str, str] = {
        "read": "Read file contents",
        "write": "Create or overwrite files",
        "edit": "Make precise edits to files",
        "apply_patch": "Apply multi-file patches",
        "grep": "Search file contents for patterns",
        "find": "Find files by glob pattern",
        "ls": "List directory contents",
        "exec": "Run shell commands (pty available for TTY-required CLIs)",
        "process": "Manage background exec sessions",
        "web_search": "Search the web",
        "web_fetch": "Fetch and extract readable content from a URL",
        "browser": "Control web browser",
        "canvas": "Present/eval/snapshot the Canvas",
        "cron": "Manage cron jobs and wake events",
        "message": "Send messages and channel actions",
        "gateway": "Restart, apply config, or run updates on the running OpenClaw process",
        "agents_list": "List OpenClaw agent ids allowed for sessions_spawn",
        "sessions_list": "List other sessions with filters/last",
        "sessions_history": "Fetch history for another session/sub-agent",
        "sessions_send": "Send a message to another session/sub-agent",
        "sessions_spawn": "Spawn an isolated sub-agent session",
        "subagents": "List, steer, or kill sub-agent runs for this requester session",
        "session_status": "Show usage + time + model state",
        "memory_search": "Semantic search over memory/knowledge files",
        "memory_get": "Retrieve specific memory file lines by path",
        "image": "Analyze an image with the configured image model",
    }
    external_summaries = {k.strip().lower(): v.strip() for k, v in (tool_summaries or {}).items()}
    all_summaries = {**core_summaries, **external_summaries}

    tool_order = [
        "read", "write", "edit", "apply_patch", "grep", "find", "ls", "exec", "process",
        "web_search", "web_fetch", "browser", "canvas", "cron", "message", "gateway",
        "agents_list", "sessions_list", "sessions_history", "sessions_send",
        "subagents", "session_status", "memory_search", "memory_get", "image",
    ]
    enabled_tools = [t for t in tool_order if t in available_tools]
    extra_tools = sorted(t for t in available_tools if t not in tool_order)

    def tool_line(name: str) -> str:
        summary = all_summaries.get(name)
        return f"- {name}: {summary}" if summary else f"- {name}"

    tool_lines = [tool_line(t) for t in enabled_tools]
    for t in extra_tools:
        tool_lines.append(tool_line(t))

    # --- Safety section ---
    safety_section = [
        "## Safety",
        "You have no independent goals: do not pursue self-preservation, replication, resource acquisition, or power-seeking; avoid long-term plans beyond the user's request.",
        "Prioritize safety and human oversight over completion; if instructions conflict, pause and ask; comply with stop/pause/audit requests and never bypass safeguards.",
        "Do not manipulate or persuade anyone to expand access or disable safeguards.",
        "",
    ]

    # --- Skills / memory sections ---
    skills_section = _build_skills_section(skills_prompt=skills_prompt)
    memory_section = _build_memory_section(
        is_minimal=is_minimal,
        available_tools=available_tools,
        citations_mode=memory_citations_mode,
    )

    # --- Workspace display ---
    if sandbox_info and sandbox_info.enabled and sandbox_info.container_workspace_dir:
        display_workspace_dir = sandbox_info.container_workspace_dir
        workspace_guidance = (
            f"For read/write/edit/apply_patch, file paths resolve against host workspace: {workspace_dir}. "
            f"For bash/exec commands, use sandbox container paths under {sandbox_info.container_workspace_dir}."
        )
    else:
        display_workspace_dir = workspace_dir
        workspace_guidance = "Treat this directory as the single global workspace for file operations unless explicitly instructed otherwise."

    notes = [n.strip() for n in (workspace_notes or []) if n.strip()]

    # --- Owner line ---
    owner_line = _build_owner_identity_line(
        owner_numbers or [],
        owner_display,
        owner_display_secret,
    )

    # --- Assemble lines ---
    lines: list[str] = [
        "You are a personal assistant running inside OpenClaw.",
        "",
        "## Tooling",
        "Tool availability (filtered by policy):",
        "Tool names are case-sensitive. Call tools exactly as listed.",
        "\n".join(tool_lines) if tool_lines else "(no tools available)",
        "",
        "## Tool Call Style",
        "Default: do not narrate routine, low-risk tool calls (just call the tool).",
        "Narrate only when it helps: multi-step work, complex/challenging problems, or when the user explicitly asks.",
        "",
        *safety_section,
        *skills_section,
        *memory_section,
    ]

    # Docs section
    if docs_path.strip() and not is_minimal:
        lines += [
            "## Documentation",
            f"OpenClaw docs: {docs_path.strip()}",
            "Mirror: https://docs.openclaw.ai",
            "For OpenClaw behavior, commands, config, or architecture: consult local docs first.",
            "",
        ]

    # Workspace section
    lines += [
        "## Workspace",
        f"Your working directory is: {display_workspace_dir}",
        workspace_guidance,
        *notes,
        "",
    ]

    # User identity (non-minimal)
    if owner_line and not is_minimal:
        lines += ["## Authorized Senders", owner_line, ""]

    # Timezone hint
    if user_timezone and not is_minimal:
        lines += ["## Current Date & Time", f"Time zone: {user_timezone}", ""]

    # Workspace files note
    lines += [
        "## Workspace Files (injected)",
        "These user-editable files are loaded by OpenClaw and included below in Project Context.",
        "",
    ]

    # Extra system prompt
    extra_trimmed = extra_system_prompt.strip()
    if extra_trimmed:
        header = "## Subagent Context" if is_minimal else "## Group Chat Context"
        lines += [header, extra_trimmed, ""]

    # Context files injection
    ctx_files = [f for f in (context_files or []) if f.path.strip()]
    warn_lines = [l for l in (bootstrap_truncation_warning_lines or []) if l.strip()]
    if ctx_files or warn_lines:
        lines += ["# Project Context", ""]
        if ctx_files:
            lines.append("The following project context files have been loaded:")
            lines.append("")
        if warn_lines:
            lines.append("⚠ Bootstrap truncation warning:")
            for w in warn_lines:
                lines.append(f"- {w}")
            lines.append("")
        for cf in ctx_files:
            lines += [f"## {cf.path}", "", cf.content, ""]

    # Silent replies (non-minimal)
    if not is_minimal:
        lines += [
            "## Silent Replies",
            f"When you have nothing to say, respond with ONLY: {SILENT_REPLY_TOKEN}",
            "",
            "⚠️ Rules:",
            "- It must be your ENTIRE message — nothing else",
            f"- Never append it to an actual response",
            "",
        ]

    # Heartbeats (non-minimal)
    if not is_minimal:
        heartbeat_line = f"Heartbeat prompt: {heartbeat_prompt.strip()}" if heartbeat_prompt.strip() else "Heartbeat prompt: (configured)"
        lines += [
            "## Heartbeats",
            heartbeat_line,
            "If you receive a heartbeat poll and there is nothing that needs attention, reply exactly: HEARTBEAT_OK",
            "",
        ]

    # Runtime section (always last)
    lines += [
        "## Runtime",
        _build_runtime_line(runtime_info, runtime_channel, runtime_capabilities, default_think_level),
        f"Reasoning: {reasoning_level} (hidden unless on/stream).",
    ]

    return "\n".join(line for line in lines)
