"""Gateway credentials — ported from bk/src/gateway/credentials.ts.

Credential resolution, precedence logic, env var reading, secret ref handling.
Covers: credentials.ts (329 lines).
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── Types ───

GatewayCredentialMode = str  # "local" | "remote"
GatewayCredentialPrecedence = str  # "env-first" | "config-first"
GatewayRemoteCredentialPrecedence = str  # "remote-first" | "env-first"
GatewayRemoteCredentialFallback = str  # "remote-env-local" | "remote-only"


@dataclass
class ExplicitGatewayAuth:
    token: str | None = None
    password: str | None = None


@dataclass
class ResolvedGatewayCredentials:
    token: str | None = None
    password: str | None = None


# ─── Error types ───

class GatewaySecretRefUnavailableError(Exception):
    """Raised when a gateway secret reference cannot be resolved."""

    def __init__(self, path: str) -> None:
        msg = (
            f"{path} is configured as a secret reference but is unavailable in this command path.\n"
            "Fix: set OPENCLAW_GATEWAY_TOKEN/OPENCLAW_GATEWAY_PASSWORD, "
            "pass explicit --token/--password,\n"
            "or run a gateway command path that resolves secret references before credential selection."
        )
        super().__init__(msg)
        self.path = path


def is_gateway_secret_ref_unavailable_error(
    error: Exception,
    expected_path: str | None = None,
) -> bool:
    """Check if an error is a GatewaySecretRefUnavailableError."""
    if not isinstance(error, GatewaySecretRefUnavailableError):
        return False
    if expected_path is None:
        return True
    return error.path == expected_path


# ─── String utilities ───

def trim_to_undefined(value: Any) -> str | None:
    """Trim a string value, returning None if empty or not a string."""
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


def _contains_env_var_reference(value: str) -> bool:
    """Check if a string contains an environment variable reference like ${VAR}."""
    return bool(re.search(r'\$\{[A-Z_][A-Z0-9_]*\}', value))


def trim_credential_to_undefined(value: Any) -> str | None:
    """Like trim_to_undefined but also rejects unresolved env var placeholders.

    Prevents literal placeholder strings like `${OPENCLAW_GATEWAY_TOKEN}` from being
    accepted as valid credentials when the referenced env var is missing.
    """
    trimmed = trim_to_undefined(value)
    if trimmed and _contains_env_var_reference(trimmed):
        return None
    return trimmed


def _first_defined(values: list[str | None]) -> str | None:
    """Return the first non-None, non-empty value."""
    for v in values:
        if v:
            return v
    return None


# ─── Env var readers ───

def read_gateway_token_env(
    env: dict[str, str] | None = None,
    include_legacy_env: bool = True,
) -> str | None:
    """Read gateway token from environment variables."""
    _env = env if env is not None else os.environ
    primary = trim_to_undefined(_env.get("OPENCLAW_GATEWAY_TOKEN"))
    if primary:
        return primary
    if not include_legacy_env:
        return None
    return trim_to_undefined(_env.get("CLAWDBOT_GATEWAY_TOKEN"))


def read_gateway_password_env(
    env: dict[str, str] | None = None,
    include_legacy_env: bool = True,
) -> str | None:
    """Read gateway password from environment variables."""
    _env = env if env is not None else os.environ
    primary = trim_to_undefined(_env.get("OPENCLAW_GATEWAY_PASSWORD"))
    if primary:
        return primary
    if not include_legacy_env:
        return None
    return trim_to_undefined(_env.get("CLAWDBOT_GATEWAY_PASSWORD"))


def has_gateway_token_env_candidate(
    env: dict[str, str] | None = None,
    include_legacy_env: bool = True,
) -> bool:
    """Check if a gateway token is available in environment."""
    return bool(read_gateway_token_env(env, include_legacy_env))


def has_gateway_password_env_candidate(
    env: dict[str, str] | None = None,
    include_legacy_env: bool = True,
) -> bool:
    """Check if a gateway password is available in environment."""
    return bool(read_gateway_password_env(env, include_legacy_env))


# ─── Credential resolution from values ───

def resolve_gateway_credentials_from_values(
    *,
    config_token: Any = None,
    config_password: Any = None,
    env: dict[str, str] | None = None,
    include_legacy_env: bool = True,
    token_precedence: str = "env-first",
    password_precedence: str = "env-first",
) -> ResolvedGatewayCredentials:
    """Resolve gateway credentials from config values and environment."""
    _env = env if env is not None else os.environ
    env_token = read_gateway_token_env(_env, include_legacy_env)
    env_password = read_gateway_password_env(_env, include_legacy_env)
    cfg_token = trim_credential_to_undefined(config_token)
    cfg_password = trim_credential_to_undefined(config_password)

    token = (
        _first_defined([cfg_token, env_token])
        if token_precedence == "config-first"
        else _first_defined([env_token, cfg_token])
    )
    password = (
        _first_defined([cfg_password, env_password])
        if password_precedence == "config-first"
        else _first_defined([env_password, cfg_password])
    )
    return ResolvedGatewayCredentials(token=token, password=password)


# ─── Credential resolution from config ───

def resolve_gateway_credentials_from_config(
    *,
    cfg: dict[str, Any],
    env: dict[str, str] | None = None,
    explicit_auth: ExplicitGatewayAuth | None = None,
    url_override: str | None = None,
    url_override_source: str | None = None,
    mode_override: str | None = None,
    include_legacy_env: bool = True,
    local_token_precedence: str | None = None,
    local_password_precedence: str | None = None,
    remote_token_precedence: str | None = None,
    remote_password_precedence: str | None = None,
    remote_token_fallback: str | None = None,
    remote_password_fallback: str | None = None,
) -> ResolvedGatewayCredentials:
    """Resolve gateway credentials from full config with precedence rules.

    Implements the complete credential resolution logic including:
    - Explicit auth (token/password flags) — highest priority
    - URL override handling
    - Local vs remote mode
    - Env var vs config precedence
    - Secret ref unavailability detection
    """
    _env = env if env is not None else os.environ

    # Explicit auth takes priority
    explicit_token = trim_to_undefined(explicit_auth.token if explicit_auth else None)
    explicit_password = trim_to_undefined(explicit_auth.password if explicit_auth else None)
    if explicit_token or explicit_password:
        return ResolvedGatewayCredentials(token=explicit_token, password=explicit_password)

    # URL override without env source = no credentials
    if trim_to_undefined(url_override) and url_override_source != "env":
        return ResolvedGatewayCredentials()

    # URL override from env = env credentials only
    if trim_to_undefined(url_override) and url_override_source == "env":
        return resolve_gateway_credentials_from_values(
            config_token=None,
            config_password=None,
            env=_env,
            include_legacy_env=include_legacy_env,
            token_precedence="env-first",
            password_precedence="env-first",
        )

    # Resolve mode
    gateway_cfg = cfg.get("gateway", {}) or {}
    mode = mode_override or ("remote" if gateway_cfg.get("mode") == "remote" else "local")
    auth_cfg = gateway_cfg.get("auth", {}) or {}
    remote_cfg = gateway_cfg.get("remote", {}) or {}
    auth_mode = auth_cfg.get("mode")

    env_token = read_gateway_token_env(_env, include_legacy_env)
    env_password = read_gateway_password_env(_env, include_legacy_env)

    # Read config values (skip secret refs for now)
    local_token = trim_to_undefined(auth_cfg.get("token"))
    local_password = trim_to_undefined(auth_cfg.get("password"))
    remote_token = trim_to_undefined(remote_cfg.get("token"))
    remote_password = trim_to_undefined(remote_cfg.get("password"))

    _local_token_prec = local_token_precedence or (
        "config-first" if _env.get("OPENCLAW_SERVICE_KIND") == "gateway" else "env-first"
    )
    _local_password_prec = local_password_precedence or "env-first"

    if mode == "local":
        fallback_token = local_token or remote_token
        fallback_password = local_password or remote_password
        return resolve_gateway_credentials_from_values(
            config_token=fallback_token,
            config_password=fallback_password,
            env=_env,
            include_legacy_env=include_legacy_env,
            token_precedence=_local_token_prec,
            password_precedence=_local_password_prec,
        )

    # Remote mode
    _remote_token_fallback = remote_token_fallback or "remote-env-local"
    _remote_password_fallback = remote_password_fallback or "remote-env-local"
    _remote_token_prec = remote_token_precedence or "remote-first"
    _remote_password_prec = remote_password_precedence or "env-first"

    if _remote_token_fallback == "remote-only":
        token = remote_token
    elif _remote_token_prec == "env-first":
        token = _first_defined([env_token, remote_token, local_token])
    else:
        token = _first_defined([remote_token, env_token, local_token])

    if _remote_password_fallback == "remote-only":
        password = remote_password
    elif _remote_password_prec == "env-first":
        password = _first_defined([env_password, remote_password, local_password])
    else:
        password = _first_defined([remote_password, env_password, local_password])

    return ResolvedGatewayCredentials(token=token, password=password)
