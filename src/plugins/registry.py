"""Plugin registry — ported from bk/src/plugins/registry.ts.

Central plugin registry: manages tools, hooks, channels, providers, commands,
services, HTTP routes, gateway handlers. Creates plugin API instances.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .types import (
    PluginCommandDefinition,
    PluginDiagnostic,
    PluginHttpRouteParams,
    PluginKind,
    PluginOrigin,
    PluginServiceDefinition,
    ProviderPlugin,
    is_plugin_hook_name,
)


@dataclass
class PluginToolRegistration:
    plugin_id: str = ""
    factory: Callable[..., Any] | None = None
    names: list[str] = field(default_factory=list)
    optional: bool = False
    source: str = ""


@dataclass
class PluginHookRegistration:
    plugin_id: str = ""
    entry: Any = None
    events: list[str] = field(default_factory=list)
    source: str = ""


@dataclass
class PluginChannelRegistration:
    plugin_id: str = ""
    plugin: Any = None
    dock: Any = None
    source: str = ""


@dataclass
class PluginProviderRegistration:
    plugin_id: str = ""
    provider: ProviderPlugin | None = None
    source: str = ""


@dataclass
class PluginServiceRegistration:
    plugin_id: str = ""
    service: PluginServiceDefinition | None = None
    source: str = ""


@dataclass
class PluginCommandRegistration:
    plugin_id: str = ""
    command: PluginCommandDefinition | None = None
    source: str = ""


@dataclass
class PluginHttpRouteRegistration:
    plugin_id: str | None = None
    path: str = ""
    handler: Callable[..., Any] | None = None
    auth: str = "gateway"
    match: str = "exact"
    source: str | None = None


@dataclass
class PluginCliRegistration:
    plugin_id: str = ""
    register: Callable[..., Any] | None = None
    commands: list[str] = field(default_factory=list)
    source: str = ""


@dataclass
class PluginRecord:
    id: str = ""
    name: str = ""
    version: str | None = None
    description: str | None = None
    kind: PluginKind | None = None
    source: str = ""
    origin: PluginOrigin = "bundled"
    workspace_dir: str | None = None
    enabled: bool = True
    status: str = "loaded"
    error: str | None = None
    tool_names: list[str] = field(default_factory=list)
    hook_names: list[str] = field(default_factory=list)
    channel_ids: list[str] = field(default_factory=list)
    provider_ids: list[str] = field(default_factory=list)
    gateway_methods: list[str] = field(default_factory=list)
    cli_commands: list[str] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    http_routes: int = 0
    hook_count: int = 0
    config_schema: bool = False
    config_ui_hints: dict[str, Any] | None = None
    config_json_schema: dict[str, Any] | None = None


@dataclass
class PluginRegistry:
    plugins: list[PluginRecord] = field(default_factory=list)
    tools: list[PluginToolRegistration] = field(default_factory=list)
    hooks: list[PluginHookRegistration] = field(default_factory=list)
    typed_hooks: list[Any] = field(default_factory=list)
    channels: list[PluginChannelRegistration] = field(default_factory=list)
    providers: list[PluginProviderRegistration] = field(default_factory=list)
    gateway_handlers: dict[str, Any] = field(default_factory=dict)
    http_routes: list[PluginHttpRouteRegistration] = field(default_factory=list)
    cli_registrars: list[PluginCliRegistration] = field(default_factory=list)
    services: list[PluginServiceRegistration] = field(default_factory=list)
    commands: list[PluginCommandRegistration] = field(default_factory=list)
    diagnostics: list[PluginDiagnostic] = field(default_factory=list)


def create_empty_plugin_registry() -> PluginRegistry:
    return PluginRegistry()


def create_plugin_registry(logger: Any = None, runtime: Any = None, core_gateway_handlers: dict[str, Any] | None = None) -> tuple[PluginRegistry, Callable[..., Any]]:
    registry = create_empty_plugin_registry()
    core_methods = set((core_gateway_handlers or {}).keys())

    def push_diagnostic(diag: PluginDiagnostic) -> None:
        registry.diagnostics.append(diag)

    def register_tool(record: PluginRecord, tool: Any, opts: dict[str, Any] | None = None) -> None:
        names = []
        if opts:
            if "names" in opts:
                names = opts["names"]
            elif "name" in opts:
                names = [opts["name"]]
        optional = (opts or {}).get("optional", False)
        registry.tools.append(PluginToolRegistration(
            plugin_id=record.id, factory=tool if callable(tool) else lambda _: tool,
            names=names, optional=optional, source=record.source,
        ))
        record.tool_names.extend(names)

    def register_channel(record: PluginRecord, plugin: Any) -> None:
        pid = getattr(plugin, "id", "") or ""
        if not pid:
            push_diagnostic(PluginDiagnostic(level="error", plugin_id=record.id, source=record.source, message="channel registration missing id"))
            return
        record.channel_ids.append(pid)
        registry.channels.append(PluginChannelRegistration(plugin_id=record.id, plugin=plugin, source=record.source))

    def register_provider(record: PluginRecord, provider: ProviderPlugin) -> None:
        if not provider.id:
            push_diagnostic(PluginDiagnostic(level="error", plugin_id=record.id, source=record.source, message="provider registration missing id"))
            return
        existing = next((p for p in registry.providers if p.provider and p.provider.id == provider.id), None)
        if existing:
            push_diagnostic(PluginDiagnostic(level="error", plugin_id=record.id, source=record.source, message=f"provider already registered: {provider.id}"))
            return
        record.provider_ids.append(provider.id)
        registry.providers.append(PluginProviderRegistration(plugin_id=record.id, provider=provider, source=record.source))

    def register_gateway_method(record: PluginRecord, method: str, handler: Any) -> None:
        trimmed = method.strip()
        if not trimmed or trimmed in core_methods or trimmed in registry.gateway_handlers:
            return
        registry.gateway_handlers[trimmed] = handler
        record.gateway_methods.append(trimmed)

    def register_command(record: PluginRecord, command: PluginCommandDefinition) -> None:
        if not command.name:
            return
        record.commands.append(command.name)
        registry.commands.append(PluginCommandRegistration(plugin_id=record.id, command=command, source=record.source))

    def register_service(record: PluginRecord, service: PluginServiceDefinition) -> None:
        if not service.id:
            return
        record.services.append(service.id)
        registry.services.append(PluginServiceRegistration(plugin_id=record.id, service=service, source=record.source))

    def create_api(record: PluginRecord, config: Any = None, plugin_config: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "id": record.id, "name": record.name, "version": record.version,
            "description": record.description, "source": record.source,
            "config": config, "plugin_config": plugin_config,
            "runtime": runtime, "logger": logger,
            "register_tool": lambda tool, opts=None: register_tool(record, tool, opts),
            "register_channel": lambda reg: register_channel(record, reg),
            "register_provider": lambda prov: register_provider(record, prov),
            "register_gateway_method": lambda m, h: register_gateway_method(record, m, h),
            "register_command": lambda cmd: register_command(record, cmd),
            "register_service": lambda svc: register_service(record, svc),
        }

    return registry, create_api
