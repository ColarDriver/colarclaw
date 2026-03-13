"""Gateway HTTP utilities — ported from bk/src/gateway/ http files.

HTTP common utilities, endpoint helpers, auth helpers.
Consolidates: http-common.ts, http-utils.ts, http-endpoint-helpers.ts,
  http-auth-helpers.ts.
"""
from __future__ import annotations

import json
import re
from typing import Any, Literal

# ─── http-common.ts ───

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Request-ID",
    "Access-Control-Max-Age": "86400",
}


def build_json_response(
    data: Any,
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a JSON response dict."""
    resp_headers = {"Content-Type": "application/json; charset=utf-8"}
    resp_headers.update(CORS_HEADERS)
    if headers:
        resp_headers.update(headers)
    return {
        "status": status,
        "headers": resp_headers,
        "body": json.dumps(data) if not isinstance(data, str) else data,
    }


def build_error_response(
    error: str,
    status: int = 400,
    code: str = "BAD_REQUEST",
) -> dict[str, Any]:
    return build_json_response(
        {"error": error, "code": code},
        status=status,
    )


# ─── http-utils.ts ───

_BEARER_RE = re.compile(r"^Bearer\s+(.+)$", re.IGNORECASE)


def extract_bearer_token(authorization: str | None) -> str | None:
    """Extract bearer token from Authorization header."""
    if not authorization:
        return None
    m = _BEARER_RE.match(authorization.strip())
    return m.group(1).strip() if m else None


def extract_request_id(headers: dict[str, str]) -> str | None:
    """Extract X-Request-ID from headers."""
    for key in ("X-Request-ID", "x-request-id", "X-Request-Id"):
        val = headers.get(key)
        if val:
            return val.strip()
    return None


def parse_json_body(body: str | bytes) -> Any:
    """Parse JSON body, returning None on failure."""
    try:
        raw = body if isinstance(body, str) else body.decode("utf-8")
        return json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None


# ─── http-endpoint-helpers.ts ───

def validate_required_fields(
    data: dict[str, Any],
    fields: list[str],
) -> str | None:
    """Validate that required fields are present. Returns error or None."""
    for f in fields:
        if f not in data or data[f] is None:
            return f"missing required field: {f}"
        if isinstance(data[f], str) and not data[f].strip():
            return f"empty required field: {f}"
    return None


def paginate_results(
    items: list[Any],
    offset: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    """Paginate a list of items."""
    total = len(items)
    page = items[offset:offset + limit]
    return {
        "items": page,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + limit < total,
    }


# ─── http-auth-helpers.ts ───

def build_www_authenticate_header(realm: str = "gateway") -> str:
    return f'Bearer realm="{realm}"'


def is_preflight_request(method: str) -> bool:
    return method.upper() == "OPTIONS"
