"""Gateway server implementation — ported from bk/src/gateway/server.impl.ts,
server.ts, boot.ts, server-startup.ts, server-maintenance.ts,
server-discovery.ts, server-discovery-runtime.ts, server-tailscale.ts,
server-plugins.ts, server-ws-runtime.ts, live-image-probe.ts,
live-tool-probe-utils.ts, canvas-capability.ts.

Main gateway server: initialization, boot sequence, plugin loading,
maintenance tasks, network discovery, and Tailscale integration.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ─── server.ts — Server entry point ───

async def start_gateway_server(cfg: dict[str, Any]) -> "GatewayServer":
    """Start the gateway server with the given config."""
    server = GatewayServer(cfg)
    await server.start()
    return server


# ─── boot.ts — Boot sequence ───

@dataclass
class GatewayBootContext:
    """Context assembled during the boot sequence."""
    config: dict[str, Any] = field(default_factory=dict)
    config_path: str = ""
    bind_host: str = "127.0.0.1"
    port: int = 18789
    tls_enabled: bool = False
    nix_mode: bool = False
    started_at_ms: int = 0


async def boot_gateway(cfg: dict[str, Any]) -> GatewayBootContext:
    """Execute the gateway boot sequence.

    Steps:
    1. Resolve bind host and port
    2. Resolve auth configuration
    3. Initialize TLS if configured
    4. Set up plugin registry
    5. Create HTTP server and WebSocket server
    6. Register method handlers
    7. Start channels
    8. Start cron scheduler
    9. Begin tick/health intervals
    """
    from .config_reload import resolve_runtime_config

    runtime_cfg = resolve_runtime_config(cfg)

    ctx = GatewayBootContext(
        config=cfg,
        bind_host=runtime_cfg.bind_host,
        port=runtime_cfg.port,
        tls_enabled=runtime_cfg.tls_enabled,
        nix_mode=runtime_cfg.nix_mode,
        started_at_ms=int(time.time() * 1000),
    )

    return ctx


# ─── server.impl.ts — Main server class ───

class GatewayServer:
    """Main gateway server implementation.

    Orchestrates all gateway subsystems: HTTP/WS server, channels,
    agents, sessions, cron, hooks, plugins, nodes, and health monitoring.
    """

    def __init__(self, cfg: dict[str, Any]) -> None:
        self._cfg = cfg
        self._started = False
        self._started_at_ms = 0
        self._stopped = False

        # Subsystems (lazily initialized)
        self._method_registry: Any = None
        self._broadcaster: Any = None
        self._config_reloader: Any = None
        self._cron_scheduler: Any = None
        self._health_monitor: Any = None
        self._exec_approval_mgr: Any = None
        self._node_registry: Any = None
        self._ws_message_handler: Any = None
        self._close_handler: Any = None

    async def start(self) -> None:
        """Start all gateway subsystems."""
        if self._started:
            return

        self._started_at_ms = int(time.time() * 1000)

        # Initialize subsystems
        from .methods import build_default_method_registry
        from .server_runtime import (
            GatewayBroadcaster,
            GatewayWsClient,
            create_chat_run_state,
            create_tool_event_recipient_registry,
            log_gateway_startup,
        )
        from .security import resolve_gateway_auth
        from .config_reload import ConfigReloader
        from .cron import CronScheduler
        from .channel_health import ChannelHealthMonitor
        from .exec_approvals import ExecApprovalManager
        from .nodes import NodeRegistry
        from .ws_connection import WsMessageHandler

        # Method registry
        self._method_registry = build_default_method_registry()

        # Broadcaster
        self._clients: set[GatewayWsClient] = set()
        self._broadcaster = GatewayBroadcaster(self._clients)

        # Config reloader
        self._config_reloader = ConfigReloader()

        # Cron
        self._cron_scheduler = CronScheduler(
            broadcast_fn=self._broadcaster.broadcast,
        )
        self._cron_scheduler.load_from_config(self._cfg)

        # Health monitor
        self._health_monitor = ChannelHealthMonitor(
            broadcast_fn=self._broadcaster.broadcast,
        )

        # Exec approvals
        self._exec_approval_mgr = ExecApprovalManager(
            broadcast_fn=self._broadcaster.broadcast,
        )

        # Node registry
        self._node_registry = NodeRegistry()

        # WS message handler
        self._ws_message_handler = WsMessageHandler(
            method_registry=self._method_registry,
            broadcast_fn=self._broadcaster.broadcast,
        )

        # Auth
        resolved_auth = resolve_gateway_auth(self._cfg)

        # Log startup
        from .config_reload import resolve_runtime_config
        runtime_cfg = resolve_runtime_config(self._cfg)
        log_gateway_startup(
            cfg=self._cfg,
            bind_host=runtime_cfg.bind_host,
            port=runtime_cfg.port,
            tls_enabled=runtime_cfg.tls_enabled,
            is_nix_mode=runtime_cfg.nix_mode,
        )

        # Start subsystems
        self._cron_scheduler.start()
        self._exec_approval_mgr.start()
        await self._config_reloader.start(self._cfg)

        self._started = True
        logger.info("gateway server started")

    async def stop(self, *, reason: str = "gateway stopping") -> None:
        """Stop all gateway subsystems gracefully."""
        if self._stopped:
            return
        self._stopped = True

        logger.info(f"gateway stopping: {reason}")

        # Broadcast shutdown
        if self._broadcaster:
            self._broadcaster.broadcast("shutdown", {
                "reason": reason,
            })

        # Stop subsystems in reverse order
        if self._exec_approval_mgr:
            self._exec_approval_mgr.stop()
        if self._cron_scheduler:
            self._cron_scheduler.stop()
        if self._config_reloader:
            await self._config_reloader.stop()

        # Clear state
        if self._node_registry:
            self._node_registry.clear()
        if self._health_monitor:
            self._health_monitor.clear()

        # Close client connections
        for c in list(self._clients):
            try:
                if c.socket:
                    await c.socket.close(1012, reason)
            except Exception:
                pass
        self._clients.clear()

        self._started = False
        logger.info("gateway server stopped")

    @property
    def is_running(self) -> bool:
        return self._started and not self._stopped

    @property
    def uptime_ms(self) -> int:
        if not self._started_at_ms:
            return 0
        return int(time.time() * 1000) - self._started_at_ms

    @property
    def method_registry(self) -> Any:
        return self._method_registry

    @property
    def node_registry(self) -> Any:
        return self._node_registry


# ─── server-maintenance.ts — Periodic maintenance ───

class GatewayMaintenance:
    """Handles periodic gateway maintenance tasks.

    - Expired session cleanup
    - Stale node detection
    - Dedupe map cleanup
    - Media file cleanup
    - Memory monitoring
    """

    def __init__(
        self,
        *,
        interval_ms: int = 300_000,  # 5 minutes
        on_cleanup: Callable[[], Any] | None = None,
    ) -> None:
        self._interval_ms = interval_ms
        self._on_cleanup = on_cleanup
        self._task: asyncio.Task | None = None
        self._stopped = False

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        self._stopped = True
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        while not self._stopped:
            try:
                await asyncio.sleep(self._interval_ms / 1000)
                if self._stopped:
                    break
                if self._on_cleanup:
                    result = self._on_cleanup()
                    if asyncio.iscoroutine(result):
                        await result
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"maintenance error: {e}")


# ─── server-discovery.ts & server-discovery-runtime.ts — mDNS/Bonjour ───

@dataclass
class GatewayDiscoveryInfo:
    """Gateway discovery information for local network announcements."""
    name: str = "OpenClaw Gateway"
    port: int = 18789
    protocol: str = "ws"
    host: str = "127.0.0.1"
    version: str = ""
    instance_id: str = ""


class GatewayDiscovery:
    """Handles local network discovery via mDNS/DNS-SD (Bonjour)."""

    def __init__(self, info: GatewayDiscoveryInfo) -> None:
        self._info = info
        self._active = False

    async def start(self) -> None:
        """Start advertising the gateway on the local network."""
        # In production, this would use zeroconf/bonjour
        self._active = True
        logger.info(
            f"discovery: advertising {self._info.name} "
            f"on {self._info.host}:{self._info.port}"
        )

    async def stop(self) -> None:
        """Stop advertising."""
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active


# ─── server-tailscale.ts ───

@dataclass
class TailscaleConfig:
    """Tailscale integration configuration."""
    enabled: bool = False
    hostname: str = ""
    auth_key: str = ""
    serve_enabled: bool = False
    funnel_enabled: bool = False


async def resolve_tailscale_ip() -> str | None:
    """Resolve the Tailscale IP address for this device."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "tailscale", "ip", "-4",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            ip = stdout.decode().strip()
            return ip if ip else None
    except (FileNotFoundError, OSError):
        pass
    return None


# ─── server-plugins.ts ───

@dataclass
class PluginInfo:
    """Information about a loaded plugin."""
    id: str = ""
    name: str = ""
    version: str = ""
    enabled: bool = True
    status: str = "loaded"  # "loaded" | "started" | "error" | "stopped"
    error: str | None = None
    http_routes: list[dict[str, str]] = field(default_factory=list)


class PluginManager:
    """Manages gateway plugins (extensions)."""

    def __init__(self) -> None:
        self._plugins: dict[str, PluginInfo] = {}

    def register(self, plugin: PluginInfo) -> None:
        self._plugins[plugin.id] = plugin

    def get(self, plugin_id: str) -> PluginInfo | None:
        return self._plugins.get(plugin_id)

    def list(self) -> list[PluginInfo]:
        return list(self._plugins.values())

    def get_http_routes(self) -> dict[str, list[dict[str, str]]]:
        """Get all plugin HTTP routes."""
        routes: dict[str, list[dict[str, str]]] = {}
        for plugin in self._plugins.values():
            if plugin.enabled and plugin.http_routes:
                routes[plugin.id] = plugin.http_routes
        return routes


# ─── canvas-capability.ts ───

def resolve_canvas_capabilities(cfg: dict[str, Any]) -> dict[str, bool]:
    """Resolve canvas host capabilities from config."""
    canvas_cfg = cfg.get("canvasHost", {}) or {}
    return {
        "enabled": bool(canvas_cfg.get("enabled", False)),
        "liveReload": bool(canvas_cfg.get("liveReload", False)),
    }


# ─── live-image-probe.ts / live-tool-probe-utils.ts ───

@dataclass
class ProbeResult:
    """Result of a live probe check."""
    ok: bool = True
    latency_ms: int = 0
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


async def probe_gateway(url: str, *, timeout_ms: int = 5000) -> ProbeResult:
    """Probe a gateway URL to check connectivity."""
    start = time.time()
    try:
        import aiohttp
        timeout = aiohttp.ClientTimeout(total=timeout_ms / 1000)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{url}/health") as resp:
                elapsed = int((time.time() - start) * 1000)
                if resp.status == 200:
                    return ProbeResult(ok=True, latency_ms=elapsed)
                return ProbeResult(ok=False, latency_ms=elapsed,
                                   error=f"HTTP {resp.status}")
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        return ProbeResult(ok=False, latency_ms=elapsed, error=str(e))
