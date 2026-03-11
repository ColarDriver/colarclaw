"""Bash tools shared — ported from bk/src/agents/bash-tools.shared.ts."""
from __future__ import annotations

import re
from typing import Any

MAX_OUTPUT_CHARS = 50_000
TRUNCATION_MESSAGE = "\n... (output truncated) ..."


def truncate_output(output: str, max_chars: int = MAX_OUTPUT_CHARS) -> str:
    if len(output) <= max_chars:
        return output
    half = (max_chars - len(TRUNCATION_MESSAGE)) // 2
    return output[:half] + TRUNCATION_MESSAGE + output[-half:]


def sanitize_command_output(output: str) -> str:
    """Remove ANSI escape sequences and control characters."""
    cleaned = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", output)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", cleaned)
    return cleaned


def format_exit_code_message(exit_code: int) -> str:
    if exit_code == 0:
        return "Command completed successfully"
    if exit_code == -1:
        return "Command failed to execute"
    if exit_code > 128:
        signal = exit_code - 128
        signal_names = {9: "SIGKILL", 15: "SIGTERM", 11: "SIGSEGV", 6: "SIGABRT"}
        name = signal_names.get(signal, f"signal {signal}")
        return f"Command killed by {name}"
    return f"Command exited with code {exit_code}"
