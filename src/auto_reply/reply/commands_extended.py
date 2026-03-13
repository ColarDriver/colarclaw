"""Auto-reply — slash commands and directive handling.

Ported from bk/src/auto-reply/reply/:
commands-core.ts, commands-allowlist.ts, commands-approve.ts,
commands-bash.ts, commands-compact.ts, commands-config.ts,
commands-context.ts, commands-context-report.ts,
commands-export-session.ts, commands-info.ts, commands-models.ts,
commands-plugin.ts, commands-session.ts, commands-session-abort.ts,
commands-session-store.ts, commands-setunset.ts,
commands-setunset-standard.ts, commands-slash-parse.ts,
commands-status.ts, commands-subagents.ts,
commands-subagents/action-*.ts (10 files),
commands-system-prompt.ts, commands-tts.ts, commands-types.ts,
config-commands.ts, config-value.ts, debug-commands.ts,
directive-handling.ts, directive-handling.auth.ts,
directive-handling.fast-lane.ts, directive-handling.impl.ts,
directive-handling.levels.ts, directive-handling.model.ts,
directive-handling.model-picker.ts, directive-handling.params.ts,
directive-handling.parse.ts, directive-handling.persist.ts,
directive-handling.queue-validation.ts, directive-handling.shared.ts,
directive-parsing.ts, directives.ts, exec.ts, exec/directive.ts,
queue.ts, queue/*.ts (7 files), queue-policy.ts.

Covers slash command registry, parsing, execution, and directive handling.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


# ─── Slash command types ───

@dataclass
class SlashCommand:
    """Definition of a slash command."""
    name: str = ""
    aliases: list[str] = field(default_factory=list)
    description: str = ""
    usage: str = ""
    hidden: bool = False
    admin_only: bool = False
    category: str = ""  # "session" | "model" | "config" | "system" | "agent"
    handler: Callable[..., Awaitable[str | None]] | None = None


@dataclass
class SlashParseResult:
    """Result of parsing a slash command."""
    is_command: bool = False
    command: str = ""
    args: str = ""
    raw: str = ""


def parse_slash_command(text: str) -> SlashParseResult:
    """Parse a slash command from message text."""
    stripped = text.strip()
    if not stripped.startswith("/"):
        return SlashParseResult(raw=text)

    match = re.match(r"^/([a-zA-Z][a-zA-Z0-9_-]*)\s*(.*)", stripped, re.DOTALL)
    if not match:
        return SlashParseResult(raw=text)

    return SlashParseResult(
        is_command=True,
        command=match.group(1).lower(),
        args=match.group(2).strip(),
        raw=text,
    )


# ─── Slash command registry ───

class SlashCommandRegistry:
    """Registry and dispatcher for slash commands."""

    def __init__(self) -> None:
        self._commands: dict[str, SlashCommand] = {}
        self._aliases: dict[str, str] = {}

    def register(self, cmd: SlashCommand) -> None:
        self._commands[cmd.name] = cmd
        for alias in cmd.aliases:
            self._aliases[alias] = cmd.name

    def get(self, name: str) -> SlashCommand | None:
        resolved = self._aliases.get(name, name)
        return self._commands.get(resolved)

    def list_commands(self, *, include_hidden: bool = False) -> list[SlashCommand]:
        cmds = list(self._commands.values())
        if not include_hidden:
            cmds = [c for c in cmds if not c.hidden]
        return sorted(cmds, key=lambda c: c.name)

    async def execute(
        self,
        text: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> str | None:
        """Parse and execute a slash command. Returns reply text or None."""
        parsed = parse_slash_command(text)
        if not parsed.is_command:
            return None

        cmd = self.get(parsed.command)
        if not cmd:
            return f"Unknown command: /{parsed.command}. Type /help for available commands."

        if not cmd.handler:
            return f"Command /{parsed.command} is not implemented."

        try:
            return await cmd.handler(parsed.args, context or {})
        except Exception as e:
            logger.error(f"Slash command error (/{parsed.command}): {e}")
            return f"Error: {e}"


def build_default_slash_commands() -> list[SlashCommand]:
    """Build the default set of slash commands."""
    return [
        # Session commands
        SlashCommand(name="new", aliases=["reset"],
                     description="Start a new session", category="session"),
        SlashCommand(name="compact", description="Compact session history",
                     category="session"),
        SlashCommand(name="export", description="Export session transcript",
                     category="session"),

        # Model commands
        SlashCommand(name="model", aliases=["m"],
                     description="Switch model", category="model",
                     usage="/model <provider/model>"),
        SlashCommand(name="thinking", aliases=["think"],
                     description="Set thinking mode",
                     category="model", usage="/thinking <off|low|medium|high>"),

        # Config commands
        SlashCommand(name="set", description="Set a config value",
                     category="config", usage="/set <key> <value>"),
        SlashCommand(name="unset", description="Unset a config value",
                     category="config", usage="/unset <key>"),
        SlashCommand(name="systemprompt", aliases=["sp"],
                     description="Set system prompt", category="config"),

        # System commands
        SlashCommand(name="help", aliases=["h", "?"],
                     description="Show help", category="system"),
        SlashCommand(name="status", description="Show status", category="system"),
        SlashCommand(name="info", description="Show session info", category="system"),
        SlashCommand(name="models", description="List available models",
                     category="system"),

        # Agent/subagent commands
        SlashCommand(name="spawn", description="Spawn a subagent",
                     category="agent", usage="/spawn <agent-id> <message>"),
        SlashCommand(name="agents", description="List/manage agents",
                     category="agent"),
        SlashCommand(name="focus", description="Focus on a subagent",
                     category="agent", usage="/focus <agent-id>"),
        SlashCommand(name="unfocus", description="Return to main agent",
                     category="agent"),
        SlashCommand(name="kill", description="Kill a subagent",
                     category="agent", usage="/kill <agent-id>"),

        # Utility
        SlashCommand(name="bash", description="Run a bash command",
                     category="system", admin_only=True,
                     usage="/bash <command>"),
        SlashCommand(name="approve", aliases=["ok", "y"],
                     description="Approve pending action", category="system"),
        SlashCommand(name="stop", aliases=["abort"],
                     description="Stop current generation", category="system"),
        SlashCommand(name="tts", description="Text-to-speech", category="system"),
        SlashCommand(name="context", description="Show context usage",
                     category="system"),
    ]


def create_default_slash_registry() -> SlashCommandRegistry:
    """Create a registry with all default slash commands."""
    registry = SlashCommandRegistry()
    for cmd in build_default_slash_commands():
        registry.register(cmd)
    return registry


# ─── Directive handling ───

@dataclass
class DirectiveHandlingResult:
    """Result of directive processing."""
    model_override: str | None = None
    thinking_override: str | None = None
    tools_override: list[str] | None = None
    system_prompt_override: str | None = None
    lane: str | None = None
    fast_lane: bool = False
    persist: bool = False


def handle_directives(
    directives: list[Any],
    *,
    config: dict[str, Any] | None = None,
    allowed_models: list[str] | None = None,
) -> DirectiveHandlingResult:
    """Process a list of reply directives into overrides."""
    result = DirectiveHandlingResult()

    for d in directives:
        if not isinstance(d, dict) and not hasattr(d, "type"):
            continue
        d_type = d.type if hasattr(d, "type") else d.get("type", "")
        d_value = d.value if hasattr(d, "value") else d.get("value", "")

        if d_type == "model":
            if allowed_models is None or d_value in allowed_models:
                result.model_override = d_value
        elif d_type == "thinking":
            result.thinking_override = d_value
        elif d_type == "tools":
            result.tools_override = d_value.split(",") if d_value else None
        elif d_type == "system-prompt":
            result.system_prompt_override = d_value
        elif d_type == "lane":
            result.lane = d_value
            result.fast_lane = d_value == "fast"

    return result


# ─── Queue management (queue.ts, queue/*.ts) ───

@dataclass
class QueueEntry:
    """An entry in the reply processing queue."""
    id: str = ""
    session_key: str = ""
    message: str = ""
    priority: int = 0  # Lower = higher priority
    enqueued_at_ms: int = 0
    status: str = "pending"  # "pending" | "processing" | "done" | "error"


class ReplyQueue:
    """Queue for processing inbound messages in order."""

    def __init__(self, *, max_size: int = 100):
        self._queue: list[QueueEntry] = []
        self._max_size = max_size

    def enqueue(self, entry: QueueEntry) -> bool:
        """Add an entry to the queue."""
        if len(self._queue) >= self._max_size:
            return False
        import bisect
        bisect.insort(self._queue, entry, key=lambda e: e.priority)
        return True

    def dequeue(self) -> QueueEntry | None:
        """Remove and return the next entry."""
        if not self._queue:
            return None
        return self._queue.pop(0)

    def peek(self) -> QueueEntry | None:
        return self._queue[0] if self._queue else None

    def size(self) -> int:
        return len(self._queue)

    def clear(self) -> None:
        self._queue.clear()

    def drain(self, session_key: str | None = None) -> list[QueueEntry]:
        """Drain entries, optionally filtered by session key."""
        if session_key is None:
            entries = list(self._queue)
            self._queue.clear()
            return entries
        drained = [e for e in self._queue if e.session_key == session_key]
        self._queue = [e for e in self._queue if e.session_key != session_key]
        return drained
