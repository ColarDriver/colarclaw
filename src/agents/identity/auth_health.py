"""Auth health — ported from bk/src/agents/auth-health.ts."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Literal

AuthStatus = Literal["ok", "expired", "missing", "invalid", "error"]

@dataclass
class AuthHealthResult:
    provider: str
    status: AuthStatus
    message: str = ""
    expires_at: float | None = None

def check_auth_health(provider: str, api_key: str | None = None) -> AuthHealthResult:
    if not api_key or not api_key.strip():
        return AuthHealthResult(provider=provider, status="missing", message="No API key configured")
    trimmed = api_key.strip()
    if len(trimmed) < 10:
        return AuthHealthResult(provider=provider, status="invalid", message="API key too short")
    return AuthHealthResult(provider=provider, status="ok")
