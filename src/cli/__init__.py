"""CLI framework and program builder.

Ported from bk/src/cli/ (~182 TS files, ~27k lines).

Organized into:
- program: CLI program builder, argument parsing, subcommand routing
- progress: Progress indicators (spinners, bars)
- prompt: Interactive prompts
- format: Output formatting, tables, colors
- helpers: Shared CLI utilities, duration/byte parsing
- gateway_rpc: Gateway RPC client for CLI
- register: Command registration for all subcommands
"""
from __future__ import annotations

from .program import (
    build_program,
    run_main,
    CLIContext,
    ProgramOptions,
)

__all__ = [
    "build_program",
    "run_main",
    "CLIContext",
    "ProgramOptions",
]
