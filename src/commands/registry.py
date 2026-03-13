"""Command registry and routing.

Ported from bk/src/commands/registry.ts, types.ts, shared.ts,
run-context.ts, output.ts, text-format.ts, report-lines.ts, resolve.ts.

Provides command registration, lookup, execution context,
output formatting, and argument resolution.
"""
from __future__ import annotations

import logging
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


# ─── Command definition ───

@dataclass
class CommandDef:
    """Definition of a CLI command."""
    name: str = ""
    description: str = ""
    aliases: list[str] = field(default_factory=list)
    hidden: bool = False
    category: str = ""  # "core" | "agent" | "channel" | "config" | "admin"
    usage: str = ""
    examples: list[str] = field(default_factory=list)
    options: list[dict[str, Any]] = field(default_factory=list)
    handler: Callable[..., Awaitable[int] | int] | None = None
    subcommands: dict[str, "CommandDef"] = field(default_factory=dict)


# ─── Run context ───

@dataclass
class RunContext:
    """Execution context for a command run."""
    command: str = ""
    args: list[str] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    cwd: str = ""
    verbose: bool = False
    quiet: bool = False
    json_output: bool = False
    dry_run: bool = False
    started_at_ms: int = 0

    def elapsed_ms(self) -> int:
        return int(time.time() * 1000) - self.started_at_ms


# ─── Output formatting ───

class OutputFormatter:
    """Handles command output formatting (text, JSON, quiet modes)."""

    def __init__(self, *, json_mode: bool = False, quiet: bool = False):
        self.json_mode = json_mode
        self.quiet = quiet
        self._json_items: list[Any] = []

    def print(self, message: str = "") -> None:
        if self.quiet:
            return
        if self.json_mode:
            self._json_items.append(message)
        else:
            print(message)

    def print_error(self, message: str) -> None:
        print(message, file=sys.stderr)

    def print_table(self, headers: list[str], rows: list[list[str]]) -> None:
        if self.json_mode:
            self._json_items.append({
                "headers": headers,
                "rows": rows,
            })
            return
        if self.quiet:
            return
        # Simple table formatting
        widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(widths):
                    widths[i] = max(widths[i], len(str(cell)))
        # Header
        header_line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
        print(header_line)
        print("  ".join("-" * w for w in widths))
        # Rows
        for row in rows:
            line = "  ".join(
                str(cell).ljust(widths[i]) if i < len(widths) else str(cell)
                for i, cell in enumerate(row)
            )
            print(line)

    def flush_json(self) -> None:
        if self.json_mode and self._json_items:
            import json
            print(json.dumps(self._json_items, indent=2, ensure_ascii=False))
            self._json_items.clear()


# ─── Report lines ───

def format_report_line(label: str, value: str, *, indent: int = 0) -> str:
    """Format a key-value report line."""
    prefix = "  " * indent
    return f"{prefix}{label}: {value}"


def format_report_section(title: str, lines: list[str]) -> str:
    """Format a section with title and indented lines."""
    parts = [title]
    for line in lines:
        parts.append(f"  {line}")
    return "\n".join(parts)


# ─── Command registry ───

class CommandRegistry:
    """Registry for CLI commands.

    Manages command definitions, lookup, alias resolution,
    and subcommand routing.
    """

    def __init__(self) -> None:
        self._commands: dict[str, CommandDef] = {}
        self._aliases: dict[str, str] = {}

    def register(self, cmd: CommandDef) -> None:
        """Register a command definition."""
        self._commands[cmd.name] = cmd
        for alias in cmd.aliases:
            self._aliases[alias] = cmd.name

    def get(self, name: str) -> CommandDef | None:
        """Look up a command by name or alias."""
        resolved = self._aliases.get(name, name)
        return self._commands.get(resolved)

    def list_commands(self, *, include_hidden: bool = False) -> list[CommandDef]:
        """List all registered commands."""
        cmds = list(self._commands.values())
        if not include_hidden:
            cmds = [c for c in cmds if not c.hidden]
        return sorted(cmds, key=lambda c: c.name)

    def list_by_category(self) -> dict[str, list[CommandDef]]:
        """List commands grouped by category."""
        groups: dict[str, list[CommandDef]] = {}
        for cmd in self._commands.values():
            if cmd.hidden:
                continue
            cat = cmd.category or "other"
            if cat not in groups:
                groups[cat] = []
            groups[cat].append(cmd)
        return {k: sorted(v, key=lambda c: c.name) for k, v in groups.items()}

    async def execute(self, name: str, ctx: RunContext) -> int:
        """Execute a command by name."""
        cmd = self.get(name)
        if not cmd:
            logger.error(f"Unknown command: {name}")
            return 1
        if not cmd.handler:
            logger.error(f"Command has no handler: {name}")
            return 1
        try:
            result = cmd.handler(ctx)
            if hasattr(result, "__await__"):
                return await result
            return result
        except KeyboardInterrupt:
            return 130
        except Exception as e:
            logger.error(f"Command error ({name}): {e}")
            return 1


# ─── Built-in command stubs ───

def _build_default_commands() -> list[CommandDef]:
    """Build the default set of CLI commands."""
    return [
        CommandDef(name="agent", description="Run an agent", category="core",
                   usage="openclaw agent [options] [message]"),
        CommandDef(name="send", description="Send a message", category="core",
                   usage="openclaw send [options] <message>"),
        CommandDef(name="config", description="Manage configuration", category="config",
                   usage="openclaw config <subcommand>",
                   subcommands={
                       "get": CommandDef(name="get", description="Get a config value"),
                       "set": CommandDef(name="set", description="Set a config value"),
                       "edit": CommandDef(name="edit", description="Edit config in editor"),
                       "path": CommandDef(name="path", description="Show config file path"),
                       "validate": CommandDef(name="validate", description="Validate config"),
                   }),
        CommandDef(name="gateway", description="Manage the gateway", category="core",
                   usage="openclaw gateway <subcommand>",
                   subcommands={
                       "run": CommandDef(name="run", description="Start the gateway"),
                       "status": CommandDef(name="status", description="Show gateway status"),
                       "stop": CommandDef(name="stop", description="Stop the gateway"),
                   }),
        CommandDef(name="channels", description="Manage channels", category="channel",
                   usage="openclaw channels <subcommand>",
                   subcommands={
                       "status": CommandDef(name="status", description="Show channel status"),
                       "add": CommandDef(name="add", description="Add a channel"),
                       "remove": CommandDef(name="remove", description="Remove a channel"),
                   }),
        CommandDef(name="sessions", description="Manage sessions", category="core",
                   usage="openclaw sessions <subcommand>",
                   subcommands={
                       "list": CommandDef(name="list", description="List sessions"),
                       "cleanup": CommandDef(name="cleanup", description="Cleanup old sessions"),
                   }),
        CommandDef(name="status", description="Show system status", category="core",
                   usage="openclaw status [--all] [--deep]"),
        CommandDef(name="doctor", description="Run diagnostics", category="admin",
                   usage="openclaw doctor"),
        CommandDef(name="login", description="Log in to OpenClaw", category="admin",
                   usage="openclaw login"),
        CommandDef(name="setup", description="Interactive setup wizard", category="admin",
                   usage="openclaw setup", aliases=["onboard", "configure"]),
        CommandDef(name="version", description="Show version", category="admin",
                   usage="openclaw version", aliases=["--version", "-v"]),
    ]


def create_default_registry() -> CommandRegistry:
    """Create a registry with all default commands registered."""
    registry = CommandRegistry()
    for cmd in _build_default_commands():
        registry.register(cmd)
    return registry
