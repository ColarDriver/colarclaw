"""Plugin runtime — ported from bk/src/plugins/runtime/ (15 TS files) + runtime.ts.

Plugin runtime environment: core, channel, config, events, logging, media,
system, tools, subagent, gateway request scope, WhatsApp integration.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from .registry import PluginRegistry


# ─── Runtime logger ───
@dataclass
class RuntimeLogger:
    debug: Callable[..., None] | None = None
    info: Callable[..., None] | None = None
    warn: Callable[..., None] | None = None
    error: Callable[..., None] | None = None


# ─── Subagent types ───
@dataclass
class SubagentRunParams:
    session_key: str = ""
    message: str = ""
    extra_system_prompt: str | None = None
    lane: str | None = None
    deliver: bool = False
    idempotency_key: str | None = None


@dataclass
class SubagentRunResult:
    run_id: str = ""


@dataclass
class SubagentWaitParams:
    run_id: str = ""
    timeout_ms: int | None = None


@dataclass
class SubagentWaitResult:
    status: str = "ok"  # "ok" | "error" | "timeout"
    error: str | None = None


@dataclass
class SubagentGetSessionMessagesParams:
    session_key: str = ""
    limit: int | None = None


@dataclass
class SubagentGetSessionMessagesResult:
    messages: list[Any] = field(default_factory=list)


@dataclass
class SubagentDeleteSessionParams:
    session_key: str = ""
    delete_transcript: bool = False


# ─── Runtime core ───
@dataclass
class PluginRuntimeConfig:
    load_config: Callable[..., Any] | None = None
    write_config_file: Callable[..., Any] | None = None


@dataclass
class PluginRuntimeSystem:
    enqueue_system_event: Callable[..., Any] | None = None
    request_heartbeat_now: Callable[..., Any] | None = None
    run_command_with_timeout: Callable[..., Any] | None = None
    format_native_dependency_hint: Callable[..., str] | None = None


@dataclass
class PluginRuntimeMedia:
    load_web_media: Callable[..., Any] | None = None
    detect_mime: Callable[..., Any] | None = None
    media_kind_from_mime: Callable[..., Any] | None = None
    is_voice_compatible_audio: Callable[..., bool] | None = None
    get_image_metadata: Callable[..., Any] | None = None
    resize_to_jpeg: Callable[..., Any] | None = None


@dataclass
class PluginRuntimeTts:
    text_to_speech_telephony: Callable[..., Any] | None = None


@dataclass
class PluginRuntimeStt:
    transcribe_audio_file: Callable[..., Any] | None = None


@dataclass
class PluginRuntimeTools:
    create_memory_get_tool: Callable[..., Any] | None = None
    create_memory_search_tool: Callable[..., Any] | None = None
    register_memory_cli: Callable[..., Any] | None = None


@dataclass
class PluginRuntimeEvents:
    on_agent_event: Callable[..., Any] | None = None
    on_session_transcript_update: Callable[..., Any] | None = None


@dataclass
class PluginRuntimeLogging:
    should_log_verbose: Callable[..., bool] | None = None
    get_child_logger: Callable[..., RuntimeLogger] | None = None


@dataclass
class PluginRuntimeState:
    resolve_state_dir: Callable[..., str] | None = None


# ─── Runtime channel ───
@dataclass
class PluginRuntimeChannel:
    session: dict[str, Callable[..., Any]] = field(default_factory=dict)
    reply: dict[str, Callable[..., Any]] = field(default_factory=dict)
    routing: dict[str, Callable[..., Any]] = field(default_factory=dict)


@dataclass
class PluginRuntimeSubagent:
    run: Callable[..., Any] | None = None
    wait_for_run: Callable[..., Any] | None = None
    get_session_messages: Callable[..., Any] | None = None
    delete_session: Callable[..., Any] | None = None


# ─── Full runtime ───
@dataclass
class PluginRuntime:
    version: str = "0.0.0"
    config: PluginRuntimeConfig = field(default_factory=PluginRuntimeConfig)
    system: PluginRuntimeSystem = field(default_factory=PluginRuntimeSystem)
    media: PluginRuntimeMedia = field(default_factory=PluginRuntimeMedia)
    tts: PluginRuntimeTts = field(default_factory=PluginRuntimeTts)
    stt: PluginRuntimeStt = field(default_factory=PluginRuntimeStt)
    tools: PluginRuntimeTools = field(default_factory=PluginRuntimeTools)
    events: PluginRuntimeEvents = field(default_factory=PluginRuntimeEvents)
    logging: PluginRuntimeLogging = field(default_factory=PluginRuntimeLogging)
    state: PluginRuntimeState = field(default_factory=PluginRuntimeState)
    subagent: PluginRuntimeSubagent = field(default_factory=PluginRuntimeSubagent)
    channel: PluginRuntimeChannel = field(default_factory=PluginRuntimeChannel)


# ─── Gateway request scope ───
@dataclass
class GatewayRequestScope:
    method: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None
    remote_address: str | None = None


# ─── Active registry ───
_active_registry: PluginRegistry | None = None
_active_cache_key: str = ""


def set_active_plugin_registry(registry: PluginRegistry, cache_key: str = "") -> None:
    global _active_registry, _active_cache_key
    _active_registry = registry
    _active_cache_key = cache_key


def get_active_plugin_registry() -> PluginRegistry | None:
    return _active_registry


def create_plugin_runtime(options: dict[str, Any] | None = None) -> PluginRuntime:
    return PluginRuntime()
