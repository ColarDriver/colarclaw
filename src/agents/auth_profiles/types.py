"""Auth profile types — ported from bk/src/agents/auth-profiles/types.ts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

AuthProfileFailureReason = Literal[
    "auth", "auth_permanent", "format", "overloaded",
    "rate_limit", "billing", "timeout", "model_not_found",
    "session_expired", "unknown",
]


@dataclass
class ApiKeyCredential:
    type: Literal["api_key"] = "api_key"
    provider: str = ""
    key: str | None = None
    key_ref: dict[str, Any] | None = None
    email: str | None = None
    metadata: dict[str, str] | None = None


@dataclass
class TokenCredential:
    type: Literal["token"] = "token"
    provider: str = ""
    token: str | None = None
    token_ref: dict[str, Any] | None = None
    expires: float | None = None
    email: str | None = None


@dataclass
class OAuthCredential:
    type: Literal["oauth"] = "oauth"
    provider: str = ""
    access: str = ""
    refresh: str = ""
    expires: float = 0
    client_id: str | None = None
    email: str | None = None
    enterprise_url: str | None = None
    project_id: str | None = None
    account_id: str | None = None


AuthProfileCredential = ApiKeyCredential | TokenCredential | OAuthCredential


@dataclass
class ProfileUsageStats:
    last_used: float | None = None
    cooldown_until: float | None = None
    disabled_until: float | None = None
    disabled_reason: str | None = None
    error_count: int = 0
    failure_counts: dict[str, int] | None = None
    last_failure_at: float | None = None


@dataclass
class AuthProfileStore:
    version: int = 1
    profiles: dict[str, AuthProfileCredential] = field(default_factory=dict)
    order: dict[str, list[str]] | None = None
    last_good: dict[str, str] | None = None
    usage_stats: dict[str, ProfileUsageStats] | None = None


@dataclass
class AuthProfileIdRepairResult:
    config: Any = None
    changes: list[str] = field(default_factory=list)
    migrated: bool = False
    from_profile_id: str | None = None
    to_profile_id: str | None = None
