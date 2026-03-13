"""Gateway control UI — ported from bk/src/gateway/control-ui.ts,
control-ui-routing.ts, control-ui-shared.ts, control-ui-csp.ts,
control-ui-http-utils.ts, control-ui-contract.ts, server-browser.ts.

Control plane web UI: routing, CSP headers, auth, origin checks, embedding.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── control-ui-contract.ts ───

CONTROL_UI_DEFAULT_BASE_PATH = "/_"
CONTROL_UI_API_PREFIX = "/_/api"


# ─── control-ui-csp.ts — Content Security Policy ───

def build_control_ui_csp(
    *,
    nonce: str = "",
    connect_src: list[str] | None = None,
    img_src: list[str] | None = None,
) -> str:
    """Build a Content-Security-Policy header for the control UI.

    Uses strict CSP to prevent XSS and data exfiltration.
    """
    nonce_directive = f"'nonce-{nonce}'" if nonce else ""
    script_src = f"'self' {nonce_directive} 'strict-dynamic'".strip()
    style_src = f"'self' {nonce_directive} 'unsafe-inline'".strip()
    connect = " ".join(["'self'", "ws:", "wss:"] + (connect_src or []))
    img = " ".join(["'self'", "data:", "blob:"] + (img_src or []))

    directives = [
        f"default-src 'self'",
        f"script-src {script_src}",
        f"style-src {style_src}",
        f"connect-src {connect}",
        f"img-src {img}",
        f"font-src 'self' data:",
        f"object-src 'none'",
        f"base-uri 'self'",
        f"form-action 'self'",
        f"frame-ancestors 'none'",
    ]
    return "; ".join(directives)


# ─── control-ui-shared.ts — Origin check ───

@dataclass
class ControlUiRootState:
    """Root state for the control UI."""
    enabled: bool = False
    base_path: str = CONTROL_UI_DEFAULT_BASE_PATH
    static_dir: str = ""
    allowed_origins: list[str] = field(default_factory=list)
    dangerous_host_header_fallback: bool = False


def is_allowed_control_ui_origin(
    origin: str | None,
    state: ControlUiRootState,
) -> bool:
    """Check if an origin is allowed for control UI access."""
    if not origin:
        return False
    normalized = origin.strip().lower().rstrip("/")
    if not normalized:
        return False
    for prefix in ("http://localhost", "http://127.0.0.1", "http://[::1]",
                    "https://localhost", "https://127.0.0.1", "https://[::1]"):
        if normalized.startswith(prefix):
            return True
    for allowed in state.allowed_origins:
        allowed_norm = allowed.strip().lower().rstrip("/")
        if allowed_norm == normalized or allowed_norm == "*":
            return True
    return False


# ─── control-ui-routing.ts — Route matching ───

@dataclass
class ControlUiRoute:
    """A control UI route."""
    path: str = ""
    method: str = "GET"
    handler_name: str = ""


def match_control_ui_route(
    path: str,
    method: str,
    base_path: str = CONTROL_UI_DEFAULT_BASE_PATH,
) -> ControlUiRoute | None:
    """Match a request path to a control UI route."""
    if not path.startswith(base_path):
        return None
    relative = path[len(base_path):]
    if not relative:
        relative = "/"
    if relative.startswith("/api/"):
        return ControlUiRoute(path=relative, method=method.upper(), handler_name="api")
    if relative.startswith("/assets/") or relative.endswith((".js", ".css", ".ico", ".png", ".svg")):
        return ControlUiRoute(path=relative, method="GET", handler_name="static")
    if method.upper() == "GET":
        return ControlUiRoute(path=relative, method="GET", handler_name="spa")
    return None


# ─── control-ui-http-utils.ts ───

def build_cors_headers(
    origin: str | None = None,
    *,
    allow_credentials: bool = True,
    max_age: int = 3600,
) -> dict[str, str]:
    """Build CORS response headers."""
    headers: dict[str, str] = {
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Request-Id",
        "Access-Control-Max-Age": str(max_age),
    }
    if origin:
        headers["Access-Control-Allow-Origin"] = origin
    if allow_credentials:
        headers["Access-Control-Allow-Credentials"] = "true"
    return headers


# ─── server-browser.ts — Browser control ───

@dataclass
class BrowserControlConfig:
    """Configuration for browser control (headless browser for web channels)."""
    enabled: bool = False
    headless: bool = True
    executable_path: str = ""
    user_data_dir: str = ""


class BrowserControl:
    """Manages headless browser instances for web-based channels."""

    def __init__(self, config: BrowserControlConfig) -> None:
        self._config = config
        self._active = False

    async def start(self) -> None:
        if not self._config.enabled:
            return
        self._active = True
        logger.info("browser control started")

    async def stop(self) -> None:
        self._active = False
        logger.info("browser control stopped")

    @property
    def is_active(self) -> bool:
        return self._active
