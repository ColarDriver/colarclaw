"""CLI credentials — ported from bk/src/agents/cli-credentials.ts.

Reading/writing CLI credentials for Claude, Codex, Qwen, MiniMax.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

log = logging.getLogger("openclaw.agents.cli_credentials")


@dataclass
class ClaudeCliCredentialOAuth:
    type: Literal["oauth"] = "oauth"
    provider: str = "anthropic"
    access: str = ""
    refresh: str = ""
    expires: float = 0


@dataclass
class ClaudeCliCredentialToken:
    type: Literal["token"] = "token"
    provider: str = "anthropic"
    token: str = ""
    expires: float = 0


ClaudeCliCredential = ClaudeCliCredentialOAuth | ClaudeCliCredentialToken


@dataclass
class CodexCliCredential:
    type: Literal["oauth"] = "oauth"
    provider: str = "openai-codex"
    access: str = ""
    refresh: str = ""
    expires: float = 0
    account_id: str | None = None


@dataclass
class QwenCliCredential:
    type: Literal["oauth"] = "oauth"
    provider: str = "qwen-portal"
    access: str = ""
    refresh: str = ""
    expires: float = 0


@dataclass
class MiniMaxCliCredential:
    type: Literal["oauth"] = "oauth"
    provider: str = "minimax-portal"
    access: str = ""
    refresh: str = ""
    expires: float = 0


_CLAUDE_CLI_CRED_REL_PATH = ".claude/.credentials.json"
_CODEX_CLI_AUTH_FILENAME = "auth.json"
_QWEN_CLI_CRED_REL_PATH = ".qwen/oauth_creds.json"
_MINIMAX_CLI_CRED_REL_PATH = ".minimax/oauth_creds.json"

_claude_cli_cache: dict[str, Any] | None = None
_codex_cli_cache: dict[str, Any] | None = None
_qwen_cli_cache: dict[str, Any] | None = None
_minimax_cli_cache: dict[str, Any] | None = None


def reset_cli_credential_caches_for_test() -> None:
    global _claude_cli_cache, _codex_cli_cache, _qwen_cli_cache, _minimax_cli_cache
    _claude_cli_cache = None
    _codex_cli_cache = None
    _qwen_cli_cache = None
    _minimax_cli_cache = None


def _resolve_home() -> str:
    return str(Path.home())


def _resolve_claude_cli_cred_path(home_dir: str | None = None) -> str:
    base = home_dir or _resolve_home()
    return os.path.join(base, _CLAUDE_CLI_CRED_REL_PATH)


def _resolve_codex_home() -> str:
    configured = os.environ.get("CODEX_HOME", "")
    home = configured if configured else os.path.join(_resolve_home(), ".codex")
    try:
        return os.path.realpath(home)
    except Exception:
        return home


def _resolve_codex_cli_auth_path() -> str:
    return os.path.join(_resolve_codex_home(), _CODEX_CLI_AUTH_FILENAME)


def _resolve_qwen_cli_cred_path(home_dir: str | None = None) -> str:
    base = home_dir or _resolve_home()
    return os.path.join(base, _QWEN_CLI_CRED_REL_PATH)


def _resolve_minimax_cli_cred_path(home_dir: str | None = None) -> str:
    base = home_dir or _resolve_home()
    return os.path.join(base, _MINIMAX_CLI_CRED_REL_PATH)


def _load_json_file(path: str) -> Any | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_json_file(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _parse_claude_cli_oauth_credential(claude_oauth: Any) -> ClaudeCliCredential | None:
    if not claude_oauth or not isinstance(claude_oauth, dict):
        return None
    access_token = claude_oauth.get("accessToken")
    refresh_token = claude_oauth.get("refreshToken")
    expires_at = claude_oauth.get("expiresAt")
    if not isinstance(access_token, str) or not access_token:
        return None
    if not isinstance(expires_at, (int, float)) or expires_at <= 0:
        return None
    if isinstance(refresh_token, str) and refresh_token:
        return ClaudeCliCredentialOAuth(access=access_token, refresh=refresh_token, expires=expires_at)
    return ClaudeCliCredentialToken(token=access_token, expires=expires_at)


def _read_portal_cli_oauth_credentials(cred_path: str, provider: str) -> dict[str, Any] | None:
    raw = _load_json_file(cred_path)
    if not raw or not isinstance(raw, dict):
        return None
    access_token = raw.get("access_token")
    refresh_token = raw.get("refresh_token")
    expires_at = raw.get("expiry_date")
    if not isinstance(access_token, str) or not access_token:
        return None
    if not isinstance(refresh_token, str) or not refresh_token:
        return None
    if not isinstance(expires_at, (int, float)):
        return None
    return {"type": "oauth", "provider": provider, "access": access_token, "refresh": refresh_token, "expires": expires_at}


def read_claude_cli_credentials(
    allow_keychain_prompt: bool = True,
    home_dir: str | None = None,
) -> ClaudeCliCredential | None:
    cred_path = _resolve_claude_cli_cred_path(home_dir)
    raw = _load_json_file(cred_path)
    if not raw or not isinstance(raw, dict):
        return None
    return _parse_claude_cli_oauth_credential(raw.get("claudeAiOauth"))


def read_claude_cli_credentials_cached(
    ttl_ms: float = 0,
    home_dir: str | None = None,
) -> ClaudeCliCredential | None:
    global _claude_cli_cache
    now = time.time() * 1000
    cache_key = _resolve_claude_cli_cred_path(home_dir)
    if (
        ttl_ms > 0
        and _claude_cli_cache
        and _claude_cli_cache.get("cache_key") == cache_key
        and now - _claude_cli_cache.get("read_at", 0) < ttl_ms
    ):
        return _claude_cli_cache.get("value")
    value = read_claude_cli_credentials(home_dir=home_dir)
    if ttl_ms > 0:
        _claude_cli_cache = {"value": value, "read_at": now, "cache_key": cache_key}
    return value


def read_codex_cli_credentials() -> CodexCliCredential | None:
    auth_path = _resolve_codex_cli_auth_path()
    raw = _load_json_file(auth_path)
    if not raw or not isinstance(raw, dict):
        return None
    tokens = raw.get("tokens")
    if not tokens or not isinstance(tokens, dict):
        return None
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    if not isinstance(access_token, str) or not access_token:
        return None
    if not isinstance(refresh_token, str) or not refresh_token:
        return None
    try:
        mtime = os.path.getmtime(auth_path)
        expires = mtime * 1000 + 60 * 60 * 1000
    except Exception:
        expires = time.time() * 1000 + 60 * 60 * 1000
    account_id = tokens.get("account_id") if isinstance(tokens.get("account_id"), str) else None
    return CodexCliCredential(access=access_token, refresh=refresh_token, expires=expires, account_id=account_id)


def read_codex_cli_credentials_cached(ttl_ms: float = 0) -> CodexCliCredential | None:
    global _codex_cli_cache
    now = time.time() * 1000
    cache_key = _resolve_codex_cli_auth_path()
    if (
        ttl_ms > 0
        and _codex_cli_cache
        and _codex_cli_cache.get("cache_key") == cache_key
        and now - _codex_cli_cache.get("read_at", 0) < ttl_ms
    ):
        return _codex_cli_cache.get("value")
    value = read_codex_cli_credentials()
    if ttl_ms > 0:
        _codex_cli_cache = {"value": value, "read_at": now, "cache_key": cache_key}
    return value


def read_qwen_cli_credentials_cached(
    ttl_ms: float = 0,
    home_dir: str | None = None,
) -> QwenCliCredential | None:
    global _qwen_cli_cache
    now = time.time() * 1000
    cache_key = _resolve_qwen_cli_cred_path(home_dir)
    if (
        ttl_ms > 0
        and _qwen_cli_cache
        and _qwen_cli_cache.get("cache_key") == cache_key
        and now - _qwen_cli_cache.get("read_at", 0) < ttl_ms
    ):
        return _qwen_cli_cache.get("value")
    result = _read_portal_cli_oauth_credentials(cache_key, "qwen-portal")
    value = QwenCliCredential(access=result["access"], refresh=result["refresh"], expires=result["expires"]) if result else None
    if ttl_ms > 0:
        _qwen_cli_cache = {"value": value, "read_at": now, "cache_key": cache_key}
    return value


def read_minimax_cli_credentials_cached(
    ttl_ms: float = 0,
    home_dir: str | None = None,
) -> MiniMaxCliCredential | None:
    global _minimax_cli_cache
    now = time.time() * 1000
    cache_key = _resolve_minimax_cli_cred_path(home_dir)
    if (
        ttl_ms > 0
        and _minimax_cli_cache
        and _minimax_cli_cache.get("cache_key") == cache_key
        and now - _minimax_cli_cache.get("read_at", 0) < ttl_ms
    ):
        return _minimax_cli_cache.get("value")
    result = _read_portal_cli_oauth_credentials(cache_key, "minimax-portal")
    value = MiniMaxCliCredential(access=result["access"], refresh=result["refresh"], expires=result["expires"]) if result else None
    if ttl_ms > 0:
        _minimax_cli_cache = {"value": value, "read_at": now, "cache_key": cache_key}
    return value
