"""Gateway server HTTP — ported from bk/src/gateway/server-http.ts,
server/http-auth.ts, server/http-listen.ts, openai-http.ts,
openresponses-http.ts, openresponses-prompt.ts, open-responses.schema.ts,
tools-invoke-http.ts, http-common.ts, http-endpoint-helpers.ts,
server/plugins-http.ts, server/plugins-http/path-context.ts,
server/plugins-http/route-auth.ts, server/plugins-http/route-match.ts.

HTTP server: routing, auth middleware, OpenAI-compatible endpoints,
plugin HTTP routes, and server listen logic.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ─── http-common.ts — HTTP constants and helpers ───

GATEWAY_HTTP_PATHS = {
    "health": "/health",
    "status": "/status",
    "api": "/api",
    "openai_chat": "/v1/chat/completions",
    "openai_models": "/v1/models",
    "open_responses": "/v1/responses",
    "hooks": "/hooks",
    "probe": "/probe",
}

# Standard security headers
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "0",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cache-Control": "no-store",
}


def apply_security_headers(headers: dict[str, str]) -> dict[str, str]:
    """Apply standard security headers to a response."""
    return {**SECURITY_HEADERS, **headers}


# ─── http-endpoint-helpers.ts ───

def json_response(
    data: Any,
    *,
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a JSON HTTP response."""
    resp_headers = apply_security_headers(headers or {})
    resp_headers["Content-Type"] = "application/json"
    return {
        "status": status,
        "headers": resp_headers,
        "body": json.dumps(data),
    }


def error_response(
    status: int,
    message: str,
    *,
    code: str = "",
    details: Any = None,
) -> dict[str, Any]:
    """Build an error JSON response."""
    body: dict[str, Any] = {"error": {"message": message}}
    if code:
        body["error"]["code"] = code
    if details:
        body["error"]["details"] = details
    return json_response(body, status=status)


# ─── server/http-auth.ts — HTTP request auth middleware ───

@dataclass
class HttpAuthResult:
    """Result of HTTP auth check."""
    authenticated: bool = False
    token: str | None = None
    error: str | None = None
    status_code: int = 401


def authenticate_http_request(
    *,
    authorization: str | None = None,
    expected_token: str | None = None,
    expected_password: str | None = None,
    auth_mode: str = "none",
) -> HttpAuthResult:
    """Authenticate an HTTP request.

    Supports token and password auth modes.
    """
    from .security import extract_bearer_token, verify_token

    if auth_mode == "none":
        return HttpAuthResult(authenticated=True)

    if not authorization:
        return HttpAuthResult(error="missing authorization header", status_code=401)

    bearer = extract_bearer_token(authorization)
    if not bearer:
        return HttpAuthResult(error="invalid authorization format", status_code=401)

    if auth_mode in ("token", "token-or-password"):
        if expected_token and verify_token(bearer, expected_token):
            return HttpAuthResult(authenticated=True, token=bearer)
    if auth_mode in ("password", "token-or-password"):
        if expected_password and verify_token(bearer, expected_password):
            return HttpAuthResult(authenticated=True, token=bearer)

    return HttpAuthResult(error="unauthorized", status_code=401)


# ─── openai-http.ts — OpenAI-compatible /v1/chat/completions ───

@dataclass
class OpenAiChatRequest:
    """OpenAI-compatible chat completion request."""
    model: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    temperature: float | None = None
    max_tokens: int | None = None
    stream: bool = False
    tools: list[dict[str, Any]] | None = None
    tool_choice: Any = None
    top_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    stop: list[str] | None = None
    n: int = 1
    user: str | None = None


def parse_openai_chat_request(body: dict[str, Any]) -> OpenAiChatRequest:
    """Parse an OpenAI-compatible chat completion request."""
    return OpenAiChatRequest(
        model=body.get("model", ""),
        messages=body.get("messages", []),
        temperature=body.get("temperature"),
        max_tokens=body.get("max_tokens"),
        stream=body.get("stream", False),
        tools=body.get("tools"),
        tool_choice=body.get("tool_choice"),
        top_p=body.get("top_p"),
        frequency_penalty=body.get("frequency_penalty"),
        presence_penalty=body.get("presence_penalty"),
        stop=body.get("stop"),
        n=body.get("n", 1),
        user=body.get("user"),
    )


def build_openai_chat_response(
    *,
    model: str,
    content: str,
    finish_reason: str = "stop",
    usage: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Build an OpenAI-compatible chat completion response."""
    return {
        "id": f"chatcmpl-{int(time.time() * 1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": content,
            },
            "finish_reason": finish_reason,
        }],
        "usage": usage or {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }


def build_openai_stream_chunk(
    *,
    model: str,
    content: str = "",
    finish_reason: str | None = None,
) -> dict[str, Any]:
    """Build an OpenAI-compatible streaming chunk."""
    delta: dict[str, Any] = {}
    if content:
        delta["content"] = content
    if finish_reason is None and not content:
        delta["role"] = "assistant"
    return {
        "id": f"chatcmpl-{int(time.time() * 1000)}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "delta": delta,
            "finish_reason": finish_reason,
        }],
    }


# ─── open-responses.schema.ts — OpenAI Responses API ───

@dataclass
class OpenResponsesRequest:
    """OpenAI Responses API request."""
    model: str = ""
    input: Any = None  # str | list[dict]
    instructions: str | None = None
    tools: list[dict[str, Any]] | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    stream: bool = False
    metadata: dict[str, Any] | None = None


def parse_open_responses_request(body: dict[str, Any]) -> OpenResponsesRequest:
    """Parse an OpenAI Responses API request."""
    return OpenResponsesRequest(
        model=body.get("model", ""),
        input=body.get("input"),
        instructions=body.get("instructions"),
        tools=body.get("tools"),
        temperature=body.get("temperature"),
        max_output_tokens=body.get("max_output_tokens"),
        stream=body.get("stream", False),
        metadata=body.get("metadata"),
    )


# ─── server/http-listen.ts — Server listen ───

async def listen_http_server(
    *,
    host: str = "127.0.0.1",
    port: int = 18789,
    handler: Callable[..., Any] | None = None,
) -> Any:
    """Start an HTTP server (asyncio-based).

    This is a simplified version; production would use aiohttp or similar.
    """
    try:
        from aiohttp import web

        app = web.Application()
        if handler:
            app.router.add_route("*", "/{path:.*}", handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()
        logger.info(f"HTTP server listening on {host}:{port}")
        return runner
    except ImportError:
        logger.warning("aiohttp not available, using basic asyncio server")
        return None


# ─── server/plugins-http.ts — Plugin HTTP routes ───

@dataclass
class PluginRoutePathContext:
    """Context for plugin HTTP route matching."""
    path: str = ""
    method: str = "GET"
    plugin_id: str = ""
    route_path: str = ""


def match_plugin_route(
    path: str,
    method: str,
    plugin_routes: dict[str, list[dict[str, str]]],
) -> PluginRoutePathContext | None:
    """Match a request path to a plugin HTTP route."""
    for plugin_id, routes in plugin_routes.items():
        prefix = f"/plugins/{plugin_id}"
        if not path.startswith(prefix):
            continue
        route_path = path[len(prefix):] or "/"
        for route in routes:
            route_method = route.get("method", "GET").upper()
            route_pattern = route.get("path", "/")
            if method.upper() == route_method and route_path == route_pattern:
                return PluginRoutePathContext(
                    path=path,
                    method=method.upper(),
                    plugin_id=plugin_id,
                    route_path=route_path,
                )
    return None


# ─── tools-invoke-http.ts — Tool invoke over HTTP ───

@dataclass
class ToolInvokeHttpRequest:
    """HTTP request for tool invocation."""
    tool_name: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    session_key: str | None = None
    run_id: str | None = None


@dataclass
class ToolInvokeHttpResponse:
    """HTTP response from tool invocation."""
    ok: bool = True
    result: Any = None
    error: str | None = None
    duration_ms: int = 0
