"""Auto-reply commands registry — ported from bk/src/auto-reply/commands-registry.ts + commands-registry.data.ts."""
from __future__ import annotations

import re
from typing import Any

from .types import ChatCommandDefinition, CommandNormalizeOptions


_REGISTERED_COMMANDS: list[ChatCommandDefinition] = []


def register_command(cmd: ChatCommandDefinition) -> None:
    _REGISTERED_COMMANDS.append(cmd)


def list_chat_commands() -> list[ChatCommandDefinition]:
    return list(_REGISTERED_COMMANDS)


def list_chat_commands_for_config(cfg: Any = None) -> list[ChatCommandDefinition]:
    return list(_REGISTERED_COMMANDS)


def normalize_command_body(text: str, options: CommandNormalizeOptions | None = None) -> str:
    body = text.strip()
    if options and options.bot_username:
        username = options.bot_username.strip().lower()
        if username:
            body = re.sub(rf"@{re.escape(username)}\b", "", body, flags=re.IGNORECASE).strip()
    return body


def find_command(text: str, cfg: Any = None) -> ChatCommandDefinition | None:
    normalized = normalize_command_body(text).lower()
    for cmd in _REGISTERED_COMMANDS:
        for alias in cmd.text_aliases:
            if normalized == alias.strip().lower():
                return cmd
    return None


# Register default commands
_DEFAULT_COMMANDS = [
    ChatCommandDefinition(key="status", text_aliases=["/status"], description="Show status", scope="both", category="status"),
    ChatCommandDefinition(key="stop", text_aliases=["/stop", "stop"], description="Stop current reply", scope="both", category="session"),
    ChatCommandDefinition(key="compact", text_aliases=["/compact"], description="Compact conversation", scope="both", category="session"),
    ChatCommandDefinition(key="clear", text_aliases=["/clear"], description="Clear conversation", scope="both", category="session"),
    ChatCommandDefinition(key="reset", text_aliases=["/reset"], description="Reset session", scope="both", category="session"),
    ChatCommandDefinition(key="model", text_aliases=["/model"], description="Switch model", scope="both", category="options", accepts_args=True),
    ChatCommandDefinition(key="config", text_aliases=["/config"], description="View/set config", scope="both", category="options", accepts_args=True),
    ChatCommandDefinition(key="queue", text_aliases=["/queue"], description="Queue settings", scope="both", category="options", accepts_args=True),
    ChatCommandDefinition(key="exec", text_aliases=["/exec"], description="Exec settings", scope="both", category="tools", accepts_args=True),
    ChatCommandDefinition(key="debug", text_aliases=["/debug"], description="Debug info", scope="both", category="status", accepts_args=True),
    ChatCommandDefinition(key="help", text_aliases=["/help"], description="Show help", scope="both", category="status"),
]
for _cmd in _DEFAULT_COMMANDS:
    register_command(_cmd)
