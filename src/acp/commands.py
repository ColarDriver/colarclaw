"""ACP commands — ported from bk/src/acp/commands.ts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AvailableCommand:
    name: str = ""
    description: str = ""
    input: dict[str, str] | None = None


def get_available_commands() -> list[AvailableCommand]:
    return [
        AvailableCommand(name="help", description="Show help and common commands."),
        AvailableCommand(name="commands", description="List available commands."),
        AvailableCommand(name="status", description="Show current status."),
        AvailableCommand(name="context", description="Explain context usage (list|detail|json).", input={"hint": "list | detail | json"}),
        AvailableCommand(name="whoami", description="Show sender id (alias: /id)."),
        AvailableCommand(name="id", description="Alias for /whoami."),
        AvailableCommand(name="subagents", description="List or manage sub-agents."),
        AvailableCommand(name="config", description="Read or write config (owner-only)."),
        AvailableCommand(name="debug", description="Set runtime-only overrides (owner-only)."),
        AvailableCommand(name="usage", description="Toggle usage footer (off|tokens|full)."),
        AvailableCommand(name="stop", description="Stop the current run."),
        AvailableCommand(name="restart", description="Restart the gateway (if enabled)."),
        AvailableCommand(name="dock-telegram", description="Route replies to Telegram."),
        AvailableCommand(name="dock-discord", description="Route replies to Discord."),
        AvailableCommand(name="dock-slack", description="Route replies to Slack."),
        AvailableCommand(name="activation", description="Set group activation (mention|always)."),
        AvailableCommand(name="send", description="Set send mode (on|off|inherit)."),
        AvailableCommand(name="reset", description="Reset the session (/new)."),
        AvailableCommand(name="new", description="Reset the session (/reset)."),
        AvailableCommand(name="think", description="Set thinking level (off|minimal|low|medium|high|xhigh)."),
        AvailableCommand(name="verbose", description="Set verbose mode (on|full|off)."),
        AvailableCommand(name="reasoning", description="Toggle reasoning output (on|off|stream)."),
        AvailableCommand(name="elevated", description="Toggle elevated mode (on|off)."),
        AvailableCommand(name="model", description="Select a model (list|status|<name>)."),
        AvailableCommand(name="queue", description="Adjust queue mode and options."),
        AvailableCommand(name="bash", description="Run a host command (if enabled)."),
        AvailableCommand(name="compact", description="Compact the session history."),
    ]
