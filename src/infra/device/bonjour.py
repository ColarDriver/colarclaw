"""Infra bonjour — ported from bk/src/infra/bonjour.ts,
bonjour-discovery.ts, bonjour-errors.ts, bonjour-ciao.ts.

mDNS/Bonjour service advertisement and discovery for gateway LAN discovery.
Uses zeroconf library on Python.
"""
from __future__ import annotations

import asyncio
import logging
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("infra.bonjour")


# ─── bonjour-errors.ts ───

def format_bonjour_error(err: Any) -> str:
    if isinstance(err, Exception):
        return str(err)
    return str(err)


# ─── bonjour.ts ───

@dataclass
class BonjourAdvertiseOpts:
    instance_name: str = ""
    gateway_port: int = 18789
    ssh_port: int = 22
    gateway_tls_enabled: bool = False
    gateway_tls_fingerprint_sha256: str = ""
    canvas_port: int | None = None
    tailnet_dns: str = ""
    cli_path: str = ""
    minimal: bool = False


@dataclass
class BonjourAdvertiser:
    _stop_event: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None

    async def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)


def _is_disabled_by_env() -> bool:
    import os
    from ..env import is_truthy_env_value
    if is_truthy_env_value(os.environ.get("OPENCLAW_DISABLE_BONJOUR")):
        return True
    return False


def _safe_service_name(name: str) -> str:
    trimmed = name.strip()
    return trimmed if trimmed else "OpenClaw"


async def start_gateway_bonjour_advertiser(
    opts: BonjourAdvertiseOpts,
) -> BonjourAdvertiser:
    """Start mDNS/Bonjour advertisement for gateway discovery."""
    if _is_disabled_by_env():
        return BonjourAdvertiser()

    advertiser = BonjourAdvertiser()

    try:
        from zeroconf import ServiceInfo, Zeroconf
    except ImportError:
        logger.debug("zeroconf not available; skipping mDNS advertisement")
        return advertiser

    hostname = socket.gethostname().split(".")[0].strip() or "openclaw"
    instance_name = opts.instance_name.strip() if opts.instance_name else f"{hostname} (OpenClaw)"

    txt_props: dict[str, str] = {
        "role": "gateway",
        "gatewayPort": str(opts.gateway_port),
        "lanHost": f"{hostname}.local",
        "displayName": instance_name.replace(" (OpenClaw)", "").strip() or instance_name,
        "transport": "gateway",
    }

    if opts.gateway_tls_enabled:
        txt_props["gatewayTls"] = "1"
        if opts.gateway_tls_fingerprint_sha256:
            txt_props["gatewayTlsSha256"] = opts.gateway_tls_fingerprint_sha256

    if opts.canvas_port and opts.canvas_port > 0:
        txt_props["canvasPort"] = str(opts.canvas_port)
    if opts.tailnet_dns:
        txt_props["tailnetDns"] = opts.tailnet_dns
    if not opts.minimal and opts.cli_path:
        txt_props["cliPath"] = opts.cli_path
    if not opts.minimal:
        txt_props["sshPort"] = str(opts.ssh_port)

    def advertise():
        try:
            zc = Zeroconf()
            info = ServiceInfo(
                "_openclaw-gw._tcp.local.",
                f"{_safe_service_name(instance_name)}._openclaw-gw._tcp.local.",
                addresses=[socket.inet_aton("0.0.0.0")],
                port=opts.gateway_port,
                properties=txt_props,
                server=f"{hostname}.local.",
            )
            zc.register_service(info)
            logger.info(f"bonjour: advertised gateway on port {opts.gateway_port}")

            advertiser._stop_event.wait()

            zc.unregister_service(info)
            zc.close()
        except Exception as e:
            logger.warning(f"bonjour: advertisement failed: {format_bonjour_error(e)}")

    thread = threading.Thread(target=advertise, daemon=True, name="bonjour-advertiser")
    thread.start()
    advertiser._thread = thread
    return advertiser


# ─── bonjour-discovery.ts ───

@dataclass
class DiscoveredGateway:
    name: str = ""
    host: str = ""
    port: int = 0
    addresses: list[str] = field(default_factory=list)
    txt: dict[str, str] = field(default_factory=dict)
    discovered_at: float = 0.0


@dataclass
class BonjourBrowser:
    _stop_event: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None
    _gateways: list[DiscoveredGateway] = field(default_factory=list)

    @property
    def gateways(self) -> list[DiscoveredGateway]:
        return list(self._gateways)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)


def start_gateway_bonjour_browser(
    on_found: Callable[[DiscoveredGateway], None] | None = None,
    timeout_s: float = 10.0,
) -> BonjourBrowser:
    """Browse for gateway mDNS/Bonjour services."""
    browser = BonjourBrowser()

    try:
        from zeroconf import ServiceBrowser, Zeroconf, ServiceStateChange
    except ImportError:
        logger.debug("zeroconf not available; skipping mDNS browsing")
        return browser

    def browse():
        try:
            zc = Zeroconf()

            class Listener:
                def add_service(self, zc, type_, name):
                    info = zc.get_service_info(type_, name)
                    if not info:
                        return
                    gw = DiscoveredGateway(
                        name=name,
                        host=info.server or "",
                        port=info.port or 0,
                        addresses=[socket.inet_ntoa(a) for a in info.addresses if len(a) == 4],
                        txt={k.decode(): v.decode() if isinstance(v, bytes) else str(v)
                             for k, v in (info.properties or {}).items()},
                        discovered_at=time.time(),
                    )
                    browser._gateways.append(gw)
                    if on_found:
                        on_found(gw)

                def remove_service(self, zc, type_, name):
                    pass

                def update_service(self, zc, type_, name):
                    pass

            listener = Listener()
            sb = ServiceBrowser(zc, "_openclaw-gw._tcp.local.", listener)
            browser._stop_event.wait(timeout=timeout_s)
            zc.close()
        except Exception as e:
            logger.warning(f"bonjour: browsing failed: {format_bonjour_error(e)}")

    thread = threading.Thread(target=browse, daemon=True, name="bonjour-browser")
    thread.start()
    browser._thread = thread
    return browser
