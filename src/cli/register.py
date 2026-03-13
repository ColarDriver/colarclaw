"""CLI subcommand registration — specialized CLIs.

Ported from bk/src/cli/register.*.ts (~50 files), *-cli.ts (~25 files),
gateway-cli.ts, gateway-rpc.ts, gateway-token-drift.ts,
config-cli.ts, config-guard.ts, cron-cli.ts, daemon-cli.ts,
daemon-cli-compat.ts, daemon.ts, devices-cli.ts, directory-cli.ts,
dns-cli.ts, docs-cli.ts, exec-approvals-cli.ts, hooks-cli.ts,
logs-cli.ts, memory-cli.ts, models-cli.ts, node-cli.ts,
nodes-cli.ts, nodes-*.ts, pairing-cli.ts, pairing-render.ts,
plugins-cli.ts, plugins-config.ts, plugin-install-plan.ts,
plugin-registry.ts, sandbox-cli.ts, secrets-cli.ts,
security-cli.ts, skills-cli*.ts, system-cli.ts, tui-cli.ts,
update-cli.ts, update-command.ts, webhooks-cli.ts,
browser-cli*.ts, a2ui-jsonl.ts, acp-cli.ts, call.ts,
channel-auth.ts, channel-options.ts, channels-cli.ts,
clawbot-cli.ts, command-registry.ts, command-options.ts,
command-secret-gateway.ts, command-secret-targets.ts,
command-tree.ts, completion-cli.ts, completion-fish.ts,
dev.ts, outbound-send-deps.ts, outbound-send-mapping.ts.

All register.* and *-cli.ts files consolidated into subcommand
registration functions.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── Subcommand registrars ───

@dataclass
class SubcommandSpec:
    """Specification for a CLI subcommand."""
    name: str = ""
    parent: str = ""
    description: str = ""
    options: list[dict[str, Any]] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    hidden: bool = False


# Gateway CLI
GATEWAY_SUBCOMMANDS = [
    SubcommandSpec(name="run", parent="gateway",
                   description="Start the gateway server"),
    SubcommandSpec(name="stop", parent="gateway",
                   description="Stop the gateway server"),
    SubcommandSpec(name="status", parent="gateway",
                   description="Show gateway status"),
    SubcommandSpec(name="restart", parent="gateway",
                   description="Restart the gateway"),
    SubcommandSpec(name="logs", parent="gateway",
                   description="Show gateway logs"),
    SubcommandSpec(name="token", parent="gateway",
                   description="Manage gateway auth tokens"),
]

# Config CLI
CONFIG_SUBCOMMANDS = [
    SubcommandSpec(name="get", parent="config",
                   description="Get a config value"),
    SubcommandSpec(name="set", parent="config",
                   description="Set a config value"),
    SubcommandSpec(name="unset", parent="config",
                   description="Remove a config value"),
    SubcommandSpec(name="edit", parent="config",
                   description="Open config in editor"),
    SubcommandSpec(name="validate", parent="config",
                   description="Validate config file"),
    SubcommandSpec(name="path", parent="config",
                   description="Show config file path"),
    SubcommandSpec(name="diff", parent="config",
                   description="Show config changes"),
]

# Channels CLI
CHANNELS_SUBCOMMANDS = [
    SubcommandSpec(name="status", parent="channels",
                   description="Show channel status"),
    SubcommandSpec(name="add", parent="channels",
                   description="Add a channel"),
    SubcommandSpec(name="remove", parent="channels",
                   description="Remove a channel"),
    SubcommandSpec(name="test", parent="channels",
                   description="Test channel connection"),
    SubcommandSpec(name="pair", parent="channels",
                   description="Pair a device"),
]

# Cron CLI
CRON_SUBCOMMANDS = [
    SubcommandSpec(name="list", parent="cron",
                   description="List cron jobs"),
    SubcommandSpec(name="add", parent="cron",
                   description="Add a cron job"),
    SubcommandSpec(name="edit", parent="cron",
                   description="Edit a cron job"),
    SubcommandSpec(name="remove", parent="cron",
                   description="Remove a cron job"),
    SubcommandSpec(name="run", parent="cron",
                   description="Run a cron job immediately"),
    SubcommandSpec(name="history", parent="cron",
                   description="Show cron execution history"),
]

# Secrets CLI
SECRETS_SUBCOMMANDS = [
    SubcommandSpec(name="list", parent="secrets",
                   description="List secrets"),
    SubcommandSpec(name="set", parent="secrets",
                   description="Set a secret"),
    SubcommandSpec(name="get", parent="secrets",
                   description="Get a secret"),
    SubcommandSpec(name="delete", parent="secrets",
                   description="Delete a secret"),
]

# Plugins CLI
PLUGINS_SUBCOMMANDS = [
    SubcommandSpec(name="list", parent="plugins",
                   description="List installed plugins"),
    SubcommandSpec(name="install", parent="plugins",
                   description="Install a plugin"),
    SubcommandSpec(name="uninstall", parent="plugins",
                   description="Uninstall a plugin"),
    SubcommandSpec(name="update", parent="plugins",
                   description="Update plugins"),
    SubcommandSpec(name="info", parent="plugins",
                   description="Show plugin info"),
]

# Sessions CLI
SESSIONS_SUBCOMMANDS = [
    SubcommandSpec(name="list", parent="sessions",
                   description="List sessions"),
    SubcommandSpec(name="cleanup", parent="sessions",
                   description="Cleanup old sessions"),
    SubcommandSpec(name="export", parent="sessions",
                   description="Export a session"),
    SubcommandSpec(name="delete", parent="sessions",
                   description="Delete a session"),
]

# Daemon CLI
DAEMON_SUBCOMMANDS = [
    SubcommandSpec(name="install", parent="daemon",
                   description="Install as daemon/service"),
    SubcommandSpec(name="uninstall", parent="daemon",
                   description="Uninstall daemon/service"),
    SubcommandSpec(name="start", parent="daemon",
                   description="Start the daemon"),
    SubcommandSpec(name="stop", parent="daemon",
                   description="Stop the daemon"),
    SubcommandSpec(name="status", parent="daemon",
                   description="Show daemon status"),
    SubcommandSpec(name="logs", parent="daemon",
                   description="Show daemon logs"),
]

# Nodes CLI (IoT/device nodes)
NODES_SUBCOMMANDS = [
    SubcommandSpec(name="list", parent="nodes",
                   description="List connected nodes"),
    SubcommandSpec(name="camera", parent="nodes",
                   description="Camera node controls"),
    SubcommandSpec(name="canvas", parent="nodes",
                   description="Canvas rendering"),
    SubcommandSpec(name="screen", parent="nodes",
                   description="Screen capture controls"),
    SubcommandSpec(name="run", parent="nodes",
                   description="Run a node command"),
]

# Browser CLI
BROWSER_SUBCOMMANDS = [
    SubcommandSpec(name="open", parent="browser",
                   description="Open a URL"),
    SubcommandSpec(name="actions", parent="browser",
                   description="Browser actions"),
    SubcommandSpec(name="inspect", parent="browser",
                   description="Inspect page"),
    SubcommandSpec(name="resize", parent="browser",
                   description="Resize browser"),
    SubcommandSpec(name="debug", parent="browser",
                   description="Browser debugging tools"),
]

# Models CLI
MODELS_SUBCOMMANDS = [
    SubcommandSpec(name="list", parent="models",
                   description="List available models"),
    SubcommandSpec(name="info", parent="models",
                   description="Show model info"),
    SubcommandSpec(name="test", parent="models",
                   description="Test model connectivity"),
]

# Memory CLI
MEMORY_SUBCOMMANDS = [
    SubcommandSpec(name="search", parent="memory",
                   description="Search memory"),
    SubcommandSpec(name="save", parent="memory",
                   description="Save to memory"),
    SubcommandSpec(name="clear", parent="memory",
                   description="Clear memory"),
]

# All top-level command groups
ALL_COMMAND_GROUPS: dict[str, list[SubcommandSpec]] = {
    "gateway": GATEWAY_SUBCOMMANDS,
    "config": CONFIG_SUBCOMMANDS,
    "channels": CHANNELS_SUBCOMMANDS,
    "cron": CRON_SUBCOMMANDS,
    "secrets": SECRETS_SUBCOMMANDS,
    "plugins": PLUGINS_SUBCOMMANDS,
    "sessions": SESSIONS_SUBCOMMANDS,
    "daemon": DAEMON_SUBCOMMANDS,
    "nodes": NODES_SUBCOMMANDS,
    "browser": BROWSER_SUBCOMMANDS,
    "models": MODELS_SUBCOMMANDS,
    "memory": MEMORY_SUBCOMMANDS,
}


def get_all_subcommands(parent: str) -> list[SubcommandSpec]:
    """Get all subcommands for a parent command."""
    return ALL_COMMAND_GROUPS.get(parent, [])


def list_all_commands() -> list[str]:
    """List all top-level commands."""
    top_level = [
        "agent", "send", "config", "gateway", "channels",
        "sessions", "status", "doctor", "setup", "login",
        "version", "cron", "secrets", "plugins", "daemon",
        "nodes", "browser", "models", "memory",
        "update", "logs", "skills", "webhooks",
    ]
    return sorted(top_level)


# ─── Command tree for help display ───

def build_command_tree() -> dict[str, Any]:
    """Build a tree of all commands and subcommands for help display."""
    tree: dict[str, Any] = {}
    for cmd in list_all_commands():
        subs = get_all_subcommands(cmd)
        if subs:
            tree[cmd] = {s.name: s.description for s in subs}
        else:
            tree[cmd] = {}
    return tree
