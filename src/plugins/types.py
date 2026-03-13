"""Plugin types — ported from bk/src/plugins/types.ts.

Core plugin types: definition, API, hooks, commands, config schema, service, provider.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Protocol

PluginKind = Literal["memory", "context-engine"]
PluginOrigin = Literal["bundled", "global", "workspace", "config"]

PluginHookName = Literal[
    "before_model_resolve", "before_prompt_build", "before_agent_start",
    "llm_input", "llm_output", "agent_end",
    "before_compaction", "after_compaction", "before_reset",
    "message_received", "message_sending", "message_sent",
    "before_tool_call", "after_tool_call", "tool_result_persist",
    "before_message_write", "session_start", "session_end",
    "subagent_spawning", "subagent_delivery_target", "subagent_spawned", "subagent_ended",
    "gateway_start", "gateway_stop",
]

PLUGIN_HOOK_NAMES: list[str] = [
    "before_model_resolve", "before_prompt_build", "before_agent_start",
    "llm_input", "llm_output", "agent_end",
    "before_compaction", "after_compaction", "before_reset",
    "message_received", "message_sending", "message_sent",
    "before_tool_call", "after_tool_call", "tool_result_persist",
    "before_message_write", "session_start", "session_end",
    "subagent_spawning", "subagent_delivery_target", "subagent_spawned", "subagent_ended",
    "gateway_start", "gateway_stop",
]

PROMPT_INJECTION_HOOK_NAMES = ["before_prompt_build", "before_agent_start"]

_plugin_hook_name_set = set(PLUGIN_HOOK_NAMES)


def is_plugin_hook_name(name: str) -> bool:
    return name in _plugin_hook_name_set


def is_prompt_injection_hook_name(name: str) -> bool:
    return name in PROMPT_INJECTION_HOOK_NAMES


@dataclass
class PluginLogger:
    info: Callable[[str], None] | None = None
    warn: Callable[[str], None] | None = None
    error: Callable[[str], None] | None = None
    debug: Callable[[str], None] | None = None


@dataclass
class PluginConfigUiHint:
    label: str | None = None
    help: str | None = None
    tags: list[str] | None = None
    advanced: bool = False
    sensitive: bool = False
    placeholder: str | None = None


@dataclass
class PluginConfigValidation:
    ok: bool = True
    value: Any = None
    errors: list[str] | None = None


@dataclass
class PluginDiagnostic:
    level: str = "warn"
    message: str = ""
    plugin_id: str | None = None
    source: str | None = None


@dataclass
class PluginCommandContext:
    sender_id: str | None = None
    channel: str = ""
    channel_id: str | None = None
    is_authorized_sender: bool = False
    args: str | None = None
    command_body: str = ""
    config: Any = None
    from_: str | None = None
    to: str | None = None
    account_id: str | None = None


@dataclass
class PluginCommandDefinition:
    name: str = ""
    description: str = ""
    accepts_args: bool = False
    require_auth: bool = True
    handler: Callable[..., Any] | None = None
    native_names: dict[str, str] | None = None


@dataclass
class PluginHttpRouteParams:
    path: str = ""
    handler: Callable[..., Any] | None = None
    auth: str = "gateway"
    match: str = "exact"
    replace_existing: bool = False


@dataclass
class PluginServiceDefinition:
    id: str = ""
    start: Callable[..., Any] | None = None
    stop: Callable[..., Any] | None = None


@dataclass
class ProviderAuthMethod:
    id: str = ""
    label: str = ""
    hint: str | None = None
    kind: str = "api_key"
    run: Callable[..., Any] | None = None


@dataclass
class ProviderPlugin:
    id: str = ""
    label: str = ""
    docs_path: str | None = None
    aliases: list[str] | None = None
    env_vars: list[str] | None = None
    auth: list[ProviderAuthMethod] = field(default_factory=list)


@dataclass
class PluginDefinition:
    id: str | None = None
    name: str | None = None
    description: str | None = None
    version: str | None = None
    kind: PluginKind | None = None
    config_schema: Any = None
    register: Callable[..., Any] | None = None
    activate: Callable[..., Any] | None = None


# Plugin hook event/result types
@dataclass
class PluginHookAgentContext:
    agent_id: str | None = None
    session_key: str | None = None
    session_id: str | None = None
    workspace_dir: str | None = None
    message_provider: str | None = None
    trigger: str | None = None
    channel_id: str | None = None


@dataclass
class PluginHookBeforeModelResolveEvent:
    prompt: str = ""


@dataclass
class PluginHookBeforeModelResolveResult:
    model_override: str | None = None
    provider_override: str | None = None


@dataclass
class PluginHookBeforePromptBuildEvent:
    prompt: str = ""
    messages: list[Any] = field(default_factory=list)


@dataclass
class PluginHookBeforePromptBuildResult:
    system_prompt: str | None = None
    prepend_context: str | None = None
    prepend_system_context: str | None = None
    append_system_context: str | None = None


@dataclass
class PluginHookLlmInputEvent:
    run_id: str = ""
    session_id: str = ""
    provider: str = ""
    model: str = ""
    prompt: str = ""
    images_count: int = 0


@dataclass
class PluginHookLlmOutputEvent:
    run_id: str = ""
    session_id: str = ""
    provider: str = ""
    model: str = ""
    assistant_texts: list[str] = field(default_factory=list)
    usage: dict[str, int] | None = None


@dataclass
class PluginHookAgentEndEvent:
    messages: list[Any] = field(default_factory=list)
    success: bool = True
    error: str | None = None
    duration_ms: int | None = None


@dataclass
class PluginHookBeforeToolCallEvent:
    tool_name: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    run_id: str | None = None
    tool_call_id: str | None = None


@dataclass
class PluginHookAfterToolCallEvent:
    tool_name: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: str | None = None
    duration_ms: int | None = None


@dataclass
class PluginHookMessageReceivedEvent:
    from_: str = ""
    content: str = ""
    timestamp: int | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class PluginHookMessageSendingEvent:
    to: str = ""
    content: str = ""
    metadata: dict[str, Any] | None = None


@dataclass
class PluginHookMessageSendingResult:
    content: str | None = None
    cancel: bool = False
