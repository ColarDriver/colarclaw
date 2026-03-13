"""Infra gateway — ported from bk/src/infra/gateway-lock.ts, gateway-request.ts,
gateway-session.ts, gateway.ts, gateway-auth.ts, gateway-cors.ts, gateway-health.ts,
gateway-routes.ts, gateway-websocket.ts.

Gateway server lifecycle, auth, CORS, health checks, routing, WebSocket.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable


# ─── gateway-lock.ts ───

@dataclass
class GatewayLock:
    path: str = ""
    pid: int = 0
    port: int = 0
    started_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"pid": self.pid, "port": self.port, "started_at": self.started_at}


def read_gateway_lock(path: str) -> GatewayLock | None:
    import json
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return GatewayLock(path=path, pid=data.get("pid", 0), port=data.get("port", 0),
                           started_at=data.get("started_at", 0.0))
    except (OSError, json.JSONDecodeError):
        return None


def write_gateway_lock(path: str, port: int) -> GatewayLock:
    import json
    lock = GatewayLock(path=path, pid=os.getpid(), port=port, started_at=time.time())
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(lock.to_dict(), f, indent=2)
    return lock


def remove_gateway_lock(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


# ─── gateway-auth.ts ───

@dataclass
class GatewayAuthConfig:
    enabled: bool = False
    token: str | None = None
    allowed_origins: list[str] = field(default_factory=list)


def validate_gateway_auth_token(token: str | None, expected: str | None) -> bool:
    if not expected:
        return True
    if not token:
        return False
    return token.strip() == expected.strip()


def extract_bearer_token(auth_header: str | None) -> str | None:
    if not auth_header:
        return None
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return None


# ─── gateway-cors.ts ───

def build_cors_headers(origin: str | None = None, allowed_origins: list[str] | None = None) -> dict[str, str]:
    headers = {
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With",
        "Access-Control-Max-Age": "86400",
    }
    if not allowed_origins or origin in (allowed_origins or []) or "*" in (allowed_origins or []):
        headers["Access-Control-Allow-Origin"] = origin or "*"
    else:
        headers["Access-Control-Allow-Origin"] = ""
    return headers


# ─── gateway-health.ts ───

@dataclass
class HealthCheckResult:
    healthy: bool = True
    version: str = ""
    uptime_ms: int = 0
    checks: dict[str, bool] = field(default_factory=dict)


_gateway_start_time: float = 0.0


def set_gateway_start_time(ts: float | None = None) -> None:
    global _gateway_start_time
    _gateway_start_time = ts or time.time()


def build_health_check(version: str = "0.0.0", checks: dict[str, bool] | None = None) -> HealthCheckResult:
    uptime = int((time.time() - _gateway_start_time) * 1000) if _gateway_start_time else 0
    all_checks = checks or {}
    return HealthCheckResult(
        healthy=all(all_checks.values()) if all_checks else True,
        version=version, uptime_ms=uptime, checks=all_checks,
    )


# ─── gateway-routes.ts ───

@dataclass
class GatewayRoute:
    method: str = "GET"
    path: str = ""
    handler: Callable[..., Any] | None = None
    auth: str = "none"  # "none" | "token" | "gateway"
    description: str = ""


class GatewayRouter:
    def __init__(self):
        self._routes: list[GatewayRoute] = []

    def add(self, method: str, path: str, handler: Callable[..., Any],
            auth: str = "none", description: str = "") -> None:
        self._routes.append(GatewayRoute(method=method.upper(), path=path,
                                          handler=handler, auth=auth, description=description))

    def get(self, method: str, path: str) -> GatewayRoute | None:
        for route in self._routes:
            if route.method == method.upper() and route.path == path:
                return route
        return None

    def list_routes(self) -> list[GatewayRoute]:
        return list(self._routes)

    def match(self, method: str, path: str) -> GatewayRoute | None:
        method = method.upper()
        for route in self._routes:
            if route.method == method:
                if route.path == path or path.startswith(route.path.rstrip("/") + "/"):
                    return route
        return None


# ─── gateway-session.ts ───

@dataclass
class GatewaySession:
    session_id: str = ""
    device_id: str = ""
    created_at: float = 0.0
    last_active_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


# ─── gateway-websocket.ts ───

@dataclass
class GatewayWebSocketClient:
    client_id: str = ""
    session_id: str = ""
    connected_at: float = 0.0
    subscriptions: list[str] = field(default_factory=list)


class GatewayWebSocketManager:
    def __init__(self):
        self._clients: dict[str, GatewayWebSocketClient] = {}

    def add(self, client: GatewayWebSocketClient) -> None:
        self._clients[client.client_id] = client

    def remove(self, client_id: str) -> None:
        self._clients.pop(client_id, None)

    def get(self, client_id: str) -> GatewayWebSocketClient | None:
        return self._clients.get(client_id)

    def broadcast(self, message: Any, subscription: str | None = None) -> int:
        count = 0
        for client in self._clients.values():
            if subscription and subscription not in client.subscriptions:
                continue
            count += 1
        return count

    @property
    def client_count(self) -> int:
        return len(self._clients)
