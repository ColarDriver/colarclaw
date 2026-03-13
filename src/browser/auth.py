"""Browser auth — ported from bk/src/browser/control-auth.ts + http-auth.ts + csrf.ts + bridge-auth-registry.ts.

Authentication for browser control server: token, password, CSRF protection.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from typing import Any


@dataclass
class BrowserControlAuth:
    token: str | None = None
    password: str | None = None


def resolve_browser_control_auth(cfg: Any = None) -> BrowserControlAuth:
    return BrowserControlAuth()


async def ensure_browser_control_auth(cfg: Any = None) -> dict[str, Any]:
    return {"auth": BrowserControlAuth(), "generated_token": False}


def verify_bearer_token(request_token: str, expected: str) -> bool:
    if not request_token or not expected:
        return False
    return hmac.compare_digest(request_token, expected)


def generate_csrf_token(session_id: str = "", secret: str = "") -> str:
    return hashlib.sha256(f"{session_id}:{secret}".encode()).hexdigest()[:32]


def validate_csrf_token(token: str, session_id: str = "", secret: str = "") -> bool:
    expected = generate_csrf_token(session_id, secret)
    return hmac.compare_digest(token, expected)


# Bridge auth registry
_bridge_tokens: dict[str, str] = {}


def register_bridge_token(bridge_id: str, token: str) -> None:
    _bridge_tokens[bridge_id] = token


def get_bridge_token(bridge_id: str) -> str | None:
    return _bridge_tokens.get(bridge_id)


def verify_bridge_token(bridge_id: str, token: str) -> bool:
    expected = _bridge_tokens.get(bridge_id)
    if not expected:
        return False
    return hmac.compare_digest(token, expected)
