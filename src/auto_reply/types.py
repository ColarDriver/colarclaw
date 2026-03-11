"""Auto-reply types — ported from bk/src/auto-reply/types.ts + commands-registry.types.ts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

CommandScope = Literal["text", "native", "both"]
CommandCategory = Literal["session", "options", "status", "management", "media", "tools", "docks"]
CommandArgType = Literal["string", "number", "boolean"]
CommandArgsParsing = Literal["none", "positional"]
ChunkMode = Literal["length", "newline"]
GroupActivationMode = Literal["mention", "always"]
StripHeartbeatMode = Literal["heartbeat", "message"]

CommandArgValue = str | int | float | bool
CommandArgValues = dict[str, CommandArgValue]


@dataclass
class CommandArgChoice:
    value: str = ""
    label: str = ""


@dataclass
class CommandArgDefinition:
    name: str = ""
    description: str = ""
    type: CommandArgType = "string"
    required: bool = False
    choices: list[CommandArgChoice | str] | None = None
    prefer_autocomplete: bool = False
    capture_remaining: bool = False


@dataclass
class CommandArgMenuSpec:
    arg: str = ""
    title: str | None = None


@dataclass
class ChatCommandDefinition:
    key: str = ""
    native_name: str | None = None
    description: str = ""
    text_aliases: list[str] = field(default_factory=list)
    accepts_args: bool = False
    args: list[CommandArgDefinition] | None = None
    args_parsing: CommandArgsParsing = "none"
    format_args: Callable[[CommandArgValues], str | None] | None = None
    args_menu: CommandArgMenuSpec | Literal["auto"] | None = None
    scope: CommandScope = "both"
    category: CommandCategory | None = None


@dataclass
class NativeCommandSpec:
    name: str = ""
    description: str = ""
    accepts_args: bool = False
    args: list[CommandArgDefinition] | None = None


@dataclass
class CommandNormalizeOptions:
    bot_username: str | None = None


@dataclass
class CommandDetection:
    exact: set[str] = field(default_factory=set)
    regex: str = ""


@dataclass
class CommandArgs:
    raw: str | None = None
    values: CommandArgValues | None = None


@dataclass
class CommandAuthorization:
    provider_id: str | None = None
    owner_list: list[str] = field(default_factory=list)
    sender_id: str | None = None
    sender_is_owner: bool = False
    is_authorized_sender: bool = False
    from_: str | None = None
    to: str | None = None


@dataclass
class ReplyPayload:
    text: str | None = None
    media_url: str | None = None
    media_urls: list[str] | None = None


@dataclass
class GetReplyOptions:
    on_tool_result: Callable[..., Any] | None = None
    on_block_reply: Callable[..., Any] | None = None


@dataclass
class EnvelopeFormatOptions:
    timezone: str | None = None
    include_timestamp: bool = True
    include_elapsed: bool = True
    user_timezone: str | None = None


@dataclass
class AgentEnvelopeParams:
    channel: str = ""
    from_: str | None = None
    timestamp: float | None = None
    host: str | None = None
    ip: str | None = None
    body: str = ""
    previous_timestamp: float | None = None
    envelope: EnvelopeFormatOptions | None = None
