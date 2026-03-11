"""Shell utilities — ported from bk/src/agents/shell-utils.ts."""
from __future__ import annotations
import os
import shlex
import subprocess

def resolve_shell() -> str:
    return os.environ.get("SHELL", "/bin/bash")

def escape_shell_arg(arg: str) -> str:
    return shlex.quote(arg)

def build_shell_command(args: list[str]) -> str:
    return " ".join(escape_shell_arg(a) for a in args)

def is_interactive_shell() -> bool:
    return os.isatty(0) and os.isatty(1)

def get_shell_env() -> dict[str, str]:
    return dict(os.environ)
