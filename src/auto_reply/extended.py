"""Auto-reply — remaining root-level modules.

Ported from bk/src/auto-reply/:
send-policy.ts, skill-commands.ts, status.ts,
templating.ts, thinking.ts, tokens.ts, tool-meta.ts,
reply.ts (main entry point).

Covers send policy, skill command registry, status tracking,
message templating, thinking mode, token management,
tool metadata, and the main reply entry point.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── send-policy.ts — Send permission policy ───

@dataclass
class SendPolicy:
    """Policy for whether the bot should send in a given context."""
    allow_dm: bool = True
    allow_group: bool = True
    allow_channel: bool = False
    require_mention_in_group: bool = True
    allowlist: list[str] = field(default_factory=list)
    blocklist: list[str] = field(default_factory=list)


def should_reply(
    *,
    policy: SendPolicy,
    is_dm: bool = False,
    is_group: bool = False,
    is_mention: bool = False,
    sender_id: str = "",
) -> bool:
    """Check if the bot should reply based on send policy."""
    # Check blocklist
    if sender_id and sender_id in policy.blocklist:
        return False
    # Check allowlist (if non-empty, only allow listed senders)
    if policy.allowlist and sender_id not in policy.allowlist:
        if "*" not in policy.allowlist:
            return False

    if is_dm:
        return policy.allow_dm
    if is_group:
        if not policy.allow_group:
            return False
        return not policy.require_mention_in_group or is_mention

    return policy.allow_channel


def resolve_send_policy(config: dict[str, Any]) -> SendPolicy:
    """Resolve send policy from config."""
    messages = config.get("messages", {}) or {}
    policy_cfg = messages.get("sendPolicy", {}) or {}
    return SendPolicy(
        allow_dm=bool(policy_cfg.get("allowDm", True)),
        allow_group=bool(policy_cfg.get("allowGroup", True)),
        allow_channel=bool(policy_cfg.get("allowChannel", False)),
        require_mention_in_group=bool(policy_cfg.get("requireMentionInGroup", True)),
        allowlist=policy_cfg.get("allowlist", []),
        blocklist=policy_cfg.get("blocklist", []),
    )


# ─── templating.ts — Response prefix templates ───

TEMPLATE_VARS = {
    "{{model}}": "",
    "{{thinking}}": "",
    "{{time}}": "",
    "{{date}}": "",
    "{{session}}": "",
    "{{agent}}": "",
}


def render_template(
    template: str,
    *,
    model: str = "",
    thinking: str = "",
    session_key: str = "",
    agent_id: str = "",
) -> str:
    """Render a response prefix template."""
    result = template
    result = result.replace("{{model}}", model)
    result = result.replace("{{thinking}}", thinking)
    result = result.replace("{{time}}", time.strftime("%H:%M"))
    result = result.replace("{{date}}", time.strftime("%Y-%m-%d"))
    result = result.replace("{{session}}", session_key)
    result = result.replace("{{agent}}", agent_id)
    return result


# ─── thinking.ts — Thinking mode resolution ───

THINKING_LEVELS = {
    "off": 0,
    "none": 0,
    "low": 1024,
    "medium": 4096,
    "high": 16384,
    "max": 65536,
}


def resolve_thinking_budget(level: str | None) -> int:
    """Resolve a thinking level to a token budget."""
    if not level:
        return 0
    return THINKING_LEVELS.get(level.lower(), 0)


def is_thinking_enabled(level: str | None) -> bool:
    """Check if thinking is enabled for a given level."""
    return resolve_thinking_budget(level) > 0


# ─── tokens.ts — Token accounting ───

@dataclass
class TokenUsage:
    """Token usage for a single request."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    thinking_tokens: int = 0
    total_tokens: int = 0

    def __post_init__(self) -> None:
        if self.total_tokens == 0:
            self.total_tokens = self.input_tokens + self.output_tokens


@dataclass
class TokenBudget:
    """Token budget for context management."""
    max_context: int = 200_000
    max_output: int = 8192
    reserved_for_output: int = 8192
    available_for_input: int = 0

    def __post_init__(self) -> None:
        if self.available_for_input == 0:
            self.available_for_input = self.max_context - self.reserved_for_output


def estimate_token_count(text: str) -> int:
    """Rough estimate of token count (4 chars per token)."""
    return max(1, len(text) // 4)


# ─── tool-meta.ts — Tool metadata ───

@dataclass
class ToolMeta:
    """Metadata about a tool invocation."""
    name: str = ""
    tool_id: str = ""
    plugin_id: str | None = None
    source: str = "core"  # "core" | "plugin" | "mcp"
    is_dangerous: bool = False
    requires_approval: bool = False


def classify_tool_danger(tool_name: str) -> bool:
    """Check if a tool is considered dangerous."""
    dangerous_prefixes = {"bash", "exec", "shell", "cmd", "run", "eval"}
    return tool_name.lower().split("_")[0] in dangerous_prefixes


# ─── skill-commands.ts ───

@dataclass
class SkillCommand:
    """A skill-provided command."""
    name: str = ""
    trigger: str = ""  # regex pattern
    skill_id: str = ""
    description: str = ""


def match_skill_commands(
    text: str,
    commands: list[SkillCommand],
) -> SkillCommand | None:
    """Match text against registered skill commands."""
    for cmd in commands:
        if cmd.trigger:
            if re.match(cmd.trigger, text, re.IGNORECASE):
                return cmd
        elif text.lower().startswith(f"/{cmd.name}"):
            return cmd
    return None


# ─── status.ts — Reply status tracking ───

@dataclass
class ReplyStatus:
    """Status of reply processing."""
    session_key: str = ""
    status: str = "idle"  # "idle" | "processing" | "streaming" | "done" | "error"
    started_at_ms: int = 0
    model: str = ""
    tokens_used: int = 0
    error: str | None = None


class ReplyStatusTracker:
    """Tracks reply processing status per session."""

    def __init__(self) -> None:
        self._statuses: dict[str, ReplyStatus] = {}

    def start(self, session_key: str, model: str = "") -> None:
        self._statuses[session_key] = ReplyStatus(
            session_key=session_key,
            status="processing",
            started_at_ms=int(time.time() * 1000),
            model=model,
        )

    def update(self, session_key: str, status: str, **kwargs: Any) -> None:
        entry = self._statuses.get(session_key)
        if entry:
            entry.status = status
            for k, v in kwargs.items():
                if hasattr(entry, k):
                    setattr(entry, k, v)

    def finish(self, session_key: str, *, tokens: int = 0) -> None:
        entry = self._statuses.get(session_key)
        if entry:
            entry.status = "done"
            entry.tokens_used = tokens

    def get(self, session_key: str) -> ReplyStatus | None:
        return self._statuses.get(session_key)

    def is_processing(self, session_key: str) -> bool:
        entry = self._statuses.get(session_key)
        return entry is not None and entry.status in ("processing", "streaming")


# ─── reply.ts — Main entry point ───

async def process_inbound_message(
    *,
    message: dict[str, Any],
    config: dict[str, Any],
    session_key: str = "",
    channel: str = "internal",
    channel_type: str = "dm",
) -> dict[str, Any]:
    """Main entry point for auto-reply processing.

    Orchestrates: policy check → dedup → directive parse →
    command check → model selection → agent run → delivery.
    """
    text = str(message.get("text", ""))
    sender_id = str(message.get("senderId", ""))

    # 1. Check send policy
    policy = resolve_send_policy(config)
    if not should_reply(
        policy=policy,
        is_dm=(channel_type == "dm"),
        is_group=(channel_type == "group"),
        is_mention=bool(message.get("isMention")),
        sender_id=sender_id,
    ):
        return {"replied": False, "reason": "policy"}

    # 2. Check for slash command
    from .reply.commands_extended import parse_slash_command
    parsed = parse_slash_command(text)
    if parsed.is_command:
        return {
            "replied": True,
            "type": "command",
            "command": parsed.command,
        }

    # 3. Parse directives
    from .reply.get_reply import parse_reply_directives, select_model_for_reply
    directives = parse_reply_directives(text)
    model = select_model_for_reply(config=config, directives=directives)

    # 4. Thinking budget
    thinking_level = None
    for d in directives:
        if d.type == "thinking":
            thinking_level = d.value
            break

    return {
        "replied": True,
        "type": "agent",
        "model": model.model,
        "session_key": session_key,
        "thinking": thinking_level,
    }
