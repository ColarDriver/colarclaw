"""Auto-reply command detection — ported from bk/src/auto-reply/command-detection.ts."""
from __future__ import annotations

import re
from typing import Any

from .types import CommandNormalizeOptions


def normalize_command_body(text: str, options: CommandNormalizeOptions | None = None) -> str:
    body = text.strip()
    if options and options.bot_username:
        username = options.bot_username.strip().lower()
        if username:
            body = re.sub(rf"@{re.escape(username)}\b", "", body, flags=re.IGNORECASE).strip()
    return body


def has_control_command(
    text: str | None = None,
    cfg: Any = None,
    options: CommandNormalizeOptions | None = None,
    commands: list[Any] | None = None,
) -> bool:
    if not text:
        return False
    trimmed = text.strip()
    if not trimmed:
        return False
    normalized = normalize_command_body(trimmed, options)
    if not normalized:
        return False
    lowered = normalized.lower()

    cmd_list = commands or []
    for cmd in cmd_list:
        aliases = getattr(cmd, "text_aliases", [])
        accepts_args = getattr(cmd, "accepts_args", False)
        for alias in aliases:
            n_alias = alias.strip().lower()
            if not n_alias:
                continue
            if lowered == n_alias:
                return True
            if accepts_args and lowered.startswith(n_alias):
                next_char = normalized[len(n_alias):len(n_alias) + 1] if len(normalized) > len(n_alias) else ""
                if next_char and next_char in " \t\n\r":
                    return True
    return False


ABORT_TRIGGERS = {"stop", "cancel", "abort", "/stop", "/cancel", "/abort"}


def is_abort_trigger(text: str) -> bool:
    return text.strip().lower() in ABORT_TRIGGERS


def is_control_command_message(
    text: str | None = None,
    cfg: Any = None,
    options: CommandNormalizeOptions | None = None,
    commands: list[Any] | None = None,
) -> bool:
    if not text:
        return False
    trimmed = text.strip()
    if not trimmed:
        return False
    if has_control_command(trimmed, cfg, options, commands):
        return True
    normalized = normalize_command_body(trimmed, options).strip().lower()
    return is_abort_trigger(normalized)


def has_inline_command_tokens(text: str | None = None) -> bool:
    body = text or ""
    if not body.strip():
        return False
    return bool(re.search(r"(?:^|\s)[/!][a-z]", body, re.IGNORECASE))


def should_compute_command_authorized(
    text: str | None = None,
    cfg: Any = None,
    options: CommandNormalizeOptions | None = None,
    commands: list[Any] | None = None,
) -> bool:
    return is_control_command_message(text, cfg, options, commands) or has_inline_command_tokens(text)
