"""Plugin SDK core — ported from bk/src/plugin-sdk/core.ts.

Core re-exports: plugin API types, channel plugin protocol, config, gateway.
"""
from __future__ import annotations

from typing import Any, Protocol


class OpenClawPluginApi(Protocol):
    """API surface exposed to plugins during registration."""
    id: str
    name: str
    version: str | None
    description: str | None
    source: str
    config: Any
    plugin_config: dict[str, Any] | None
    runtime: Any
    logger: Any

    def register_tool(self, tool: Any, opts: dict[str, Any] | None = None) -> None: ...
    def register_hook(self, events: str | list[str], handler: Any, opts: dict[str, Any] | None = None) -> None: ...
    def register_http_route(self, params: dict[str, Any]) -> None: ...
    def register_channel(self, registration: Any) -> None: ...
    def register_gateway_method(self, method: str, handler: Any) -> None: ...
    def register_cli(self, registrar: Any, opts: dict[str, Any] | None = None) -> None: ...
    def register_service(self, service: Any) -> None: ...
    def register_provider(self, provider: Any) -> None: ...
    def register_command(self, command: Any) -> None: ...
    def register_context_engine(self, id: str, factory: Any) -> None: ...
    def resolve_path(self, input: str) -> str: ...
    def on(self, hook_name: str, handler: Any, opts: dict[str, Any] | None = None) -> None: ...


class OpenClawPluginService(Protocol):
    id: str
    async def start(self, ctx: Any) -> None: ...
    async def stop(self, ctx: Any) -> None: ...


class ProviderAuthResult:
    def __init__(self, profiles: list[dict[str, Any]] | None = None, config_patch: dict[str, Any] | None = None, default_model: str | None = None, notes: list[str] | None = None):
        self.profiles = profiles or []
        self.config_patch = config_patch
        self.default_model = default_model
        self.notes = notes


class ProviderAuthContext:
    def __init__(self, config: Any = None, agent_dir: str | None = None, workspace_dir: str | None = None, prompter: Any = None, runtime: Any = None, is_remote: bool = False):
        self.config = config
        self.agent_dir = agent_dir
        self.workspace_dir = workspace_dir
        self.prompter = prompter
        self.runtime = runtime
        self.is_remote = is_remote
