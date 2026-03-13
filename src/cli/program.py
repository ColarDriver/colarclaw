"""CLI program builder and argument parsing.

Ported from bk/src/cli/build-program.ts, program.ts, program-context.ts,
run-main.ts, run.ts, run-loop.ts, argv.ts, windows-argv.ts,
context.ts, deps.ts, types.ts, lifecycle.ts, lifecycle-core.ts,
cli-name.ts, cli-utils.ts, banner.ts, tagline.ts,
suppress-deprecations.ts, shared.ts.

Builds the CLI program tree, parses arguments, resolves context,
and executes the selected command handler.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)

CLI_NAME = "openclaw"
VERSION = "2025.1.0"

BANNER = r"""
   ___                    ____ _
  / _ \ _ __   ___ _ __  / ___| | __ ___      __
 | | | | '_ \ / _ \ '_ \| |   | |/ _` \ \ /\ / /
 | |_| | |_) |  __/ | | | |___| | (_| |\ V  V /
  \___/| .__/ \___|_| |_|\____|_|\__,_| \_/\_/
       |_|
"""


@dataclass
class ProgramOptions:
    """Top-level CLI options."""
    verbose: bool = False
    quiet: bool = False
    json_output: bool = False
    config_path: str = ""
    log_level: str = "info"
    no_color: bool = False
    version: bool = False


@dataclass
class CLIContext:
    """Runtime context for CLI commands."""
    program_options: ProgramOptions = field(default_factory=ProgramOptions)
    config: dict[str, Any] = field(default_factory=dict)
    command_name: str = ""
    subcommand: str = ""
    args: list[str] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)
    cwd: str = ""
    started_at: float = 0.0

    def elapsed_ms(self) -> int:
        return int((time.time() - self.started_at) * 1000)


class CLIDeps:
    """Dependency container for CLI subsystems."""

    def __init__(self, *, config: dict[str, Any] | None = None):
        self._config = config

    @property
    def config(self) -> dict[str, Any]:
        if self._config is None:
            from ..config import load_config
            self._config = load_config()
        return self._config


def build_program() -> argparse.ArgumentParser:
    """Build the CLI argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog=CLI_NAME,
        description="OpenClaw — AI gateway and agent platform",
    )
    parser.add_argument("--verbose", "-V", action="store_true", help="Verbose output")
    parser.add_argument("--quiet", "-q", action="store_true", help="Quiet mode")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--config", default="", help="Config file path")
    parser.add_argument("--log-level", default="info",
                        choices=["debug", "info", "warn", "error"])
    parser.add_argument("--no-color", action="store_true", help="Disable colors")
    parser.add_argument("--version", "-v", action="store_true", help="Show version")

    subs = parser.add_subparsers(dest="command")

    # Gateway
    gw = subs.add_parser("gateway", help="Manage the gateway")
    gw_sub = gw.add_subparsers(dest="subcommand")
    gw_run = gw_sub.add_parser("run", help="Start the gateway")
    gw_run.add_argument("--port", type=int, default=18789)
    gw_run.add_argument("--bind", default="loopback", choices=["loopback", "all"])
    gw_run.add_argument("--force", action="store_true")
    gw_sub.add_parser("status", help="Show gateway status")
    gw_sub.add_parser("stop", help="Stop the gateway")

    # Agent
    agent = subs.add_parser("agent", help="Run an agent")
    agent.add_argument("message", nargs="*", help="Message to send")
    agent.add_argument("--model", "-m", help="Model to use")
    agent.add_argument("--thinking", help="Thinking mode")
    agent.add_argument("--session", "-s", help="Session key")
    agent.add_argument("--agent", "-a", help="Agent ID")
    agent.add_argument("--deliver", action="store_true")
    agent.add_argument("--channel", help="Delivery channel")

    # Config
    cfg = subs.add_parser("config", help="Manage configuration")
    cfg_sub = cfg.add_subparsers(dest="subcommand")
    cfg_get = cfg_sub.add_parser("get", help="Get config value")
    cfg_get.add_argument("path", help="Config path (dotted)")
    cfg_set = cfg_sub.add_parser("set", help="Set config value")
    cfg_set.add_argument("path", help="Config path (dotted)")
    cfg_set.add_argument("value", help="Value to set")
    cfg_sub.add_parser("edit", help="Edit config in editor")
    cfg_sub.add_parser("path", help="Show config file path")
    cfg_sub.add_parser("validate", help="Validate config")

    # Send
    send = subs.add_parser("send", help="Send a message")
    send.add_argument("message", nargs="*")
    send.add_argument("--to", required=True)
    send.add_argument("--channel")

    # Status
    status = subs.add_parser("status", help="System status")
    status.add_argument("--all", action="store_true")
    status.add_argument("--deep", action="store_true")

    # Sessions
    sess = subs.add_parser("sessions", help="Manage sessions")
    sess_sub = sess.add_subparsers(dest="subcommand")
    sess_sub.add_parser("list", help="List sessions")
    cleanup = sess_sub.add_parser("cleanup", help="Cleanup old sessions")
    cleanup.add_argument("--max-age-days", type=int, default=30)
    cleanup.add_argument("--dry-run", action="store_true")

    # Channels
    ch = subs.add_parser("channels", help="Manage channels")
    ch_sub = ch.add_subparsers(dest="subcommand")
    ch_sub.add_parser("status", help="Show channel status")

    # Doctor
    subs.add_parser("doctor", help="Run diagnostics")

    # Setup
    setup = subs.add_parser("setup", help="Interactive setup")
    setup.add_argument("--non-interactive", action="store_true")

    # Login
    subs.add_parser("login", help="Log in to OpenClaw")

    # Version
    subs.add_parser("version", help="Show version")

    # Cron
    cron = subs.add_parser("cron", help="Manage cron jobs")
    cron_sub = cron.add_subparsers(dest="subcommand")
    cron_sub.add_parser("list", help="List cron jobs")
    cron_add = cron_sub.add_parser("add", help="Add a cron job")
    cron_add.add_argument("--schedule", required=True)
    cron_add.add_argument("--command", required=True)

    # Secrets
    sec = subs.add_parser("secrets", help="Manage secrets")
    sec_sub = sec.add_subparsers(dest="subcommand")
    sec_sub.add_parser("list", help="List secrets")
    sec_set = sec_sub.add_parser("set", help="Set a secret")
    sec_set.add_argument("name")
    sec_set.add_argument("value")

    # Plugins
    plug = subs.add_parser("plugins", help="Manage plugins")
    plug_sub = plug.add_subparsers(dest="subcommand")
    plug_sub.add_parser("list", help="List plugins")
    pi = plug_sub.add_parser("install", help="Install a plugin")
    pi.add_argument("name")

    return parser


async def run_main(argv: list[str] | None = None) -> int:
    """Main entry point for the CLI."""
    parser = build_program()
    args = parser.parse_args(argv)

    if args.version or (hasattr(args, "command") and args.command == "version"):
        print(f"{CLI_NAME} {VERSION}")
        return 0

    if not hasattr(args, "command") or not args.command:
        print(BANNER)
        parser.print_help()
        return 0

    # Build context
    ctx = CLIContext(
        program_options=ProgramOptions(
            verbose=args.verbose,
            quiet=args.quiet,
            json_output=args.json,
            config_path=args.config,
            log_level=args.log_level,
            no_color=args.no_color,
        ),
        command_name=args.command,
        subcommand=getattr(args, "subcommand", ""),
        cwd=os.getcwd(),
        started_at=time.time(),
    )

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(message)s" if not args.verbose else "%(asctime)s %(levelname)s %(message)s",
    )

    # Route to handler
    try:
        from ..commands.handlers import (
            config_get, config_set, config_validate, config_path_cmd,
            send_command, SendOptions,
            status_command, channels_status,
            sessions_list, sessions_cleanup,
            doctor_command, setup_command,
        )
        from ..commands.agent import run_agent_command, parse_agent_options

        if args.command == "agent":
            opts = parse_agent_options(
                args.message or [],
                vars(args),
            )
            return await run_agent_command(opts)

        if args.command == "config":
            if args.subcommand == "get":
                return await config_get(args.path)
            if args.subcommand == "set":
                return await config_set(args.path, args.value)
            if args.subcommand == "validate":
                return await config_validate()
            if args.subcommand == "path":
                return await config_path_cmd()

        if args.command == "send":
            return await send_command(SendOptions(
                to=args.to,
                message=" ".join(args.message or []),
                channel=args.channel,
                json_output=args.json,
            ))

        if args.command == "status":
            return await status_command(
                show_all=args.all,
                deep=args.deep,
                json_output=args.json,
            )

        if args.command == "channels":
            if args.subcommand == "status":
                return await channels_status(json_output=args.json)

        if args.command == "sessions":
            if args.subcommand == "list":
                return await sessions_list(json_output=args.json)
            if args.subcommand == "cleanup":
                return await sessions_cleanup(
                    max_age_days=args.max_age_days,
                    dry_run=args.dry_run,
                )

        if args.command == "doctor":
            return await doctor_command(json_output=args.json)

        if args.command == "setup":
            return await setup_command(
                non_interactive=args.non_interactive,
            )

        print(f"Command '{args.command}' not yet implemented")
        return 1

    except KeyboardInterrupt:
        return 130
    except Exception as e:
        logger.error(f"Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1
