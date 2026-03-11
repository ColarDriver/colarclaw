"""External CLI sync — ported from bk/src/agents/auth-profiles/external-cli-sync.ts.

Syncs credentials from external CLI tools (Claude, Codex, Qwen, MiniMax).
"""
from __future__ import annotations

import time
from typing import Any

from .constants import (
    CLAUDE_CLI_PROFILE_ID, CODEX_CLI_PROFILE_ID,
    EXTERNAL_CLI_NEAR_EXPIRY_MS, EXTERNAL_CLI_SYNC_TTL_MS,
    MINIMAX_CLI_PROFILE_ID, QWEN_CLI_PROFILE_ID, log,
)
from .types import AuthProfileStore, OAuthCredential, TokenCredential


def sync_external_cli_credentials(store: AuthProfileStore) -> bool:
    """Sync credentials from external CLI tools into the auth store."""
    mutated = False
    now = time.time() * 1000

    try:
        mutated = _sync_claude_cli(store, now) or mutated
    except Exception as exc:
        log.debug("Claude CLI sync failed: %s", exc)

    try:
        mutated = _sync_codex_cli(store, now) or mutated
    except Exception as exc:
        log.debug("Codex CLI sync failed: %s", exc)

    try:
        mutated = _sync_qwen_cli(store, now) or mutated
    except Exception as exc:
        log.debug("Qwen CLI sync failed: %s", exc)

    try:
        mutated = _sync_minimax_cli(store, now) or mutated
    except Exception as exc:
        log.debug("MiniMax CLI sync failed: %s", exc)

    return mutated


def _sync_claude_cli(store: AuthProfileStore, now: float) -> bool:
    from ..cli_credentials import read_claude_cli_credentials_cached
    cred = read_claude_cli_credentials_cached(ttl_ms=EXTERNAL_CLI_SYNC_TTL_MS)
    if not cred:
        return False
    existing = store.profiles.get(CLAUDE_CLI_PROFILE_ID)
    if existing and hasattr(existing, "expires"):
        if existing.expires and existing.expires > now + EXTERNAL_CLI_NEAR_EXPIRY_MS:
            return False
    if hasattr(cred, "access"):
        store.profiles[CLAUDE_CLI_PROFILE_ID] = OAuthCredential(
            provider="anthropic", access=cred.access,
            refresh=cred.refresh, expires=cred.expires,
        )
    elif hasattr(cred, "token"):
        store.profiles[CLAUDE_CLI_PROFILE_ID] = TokenCredential(
            provider="anthropic", token=cred.token, expires=cred.expires,
        )
    return True


def _sync_codex_cli(store: AuthProfileStore, now: float) -> bool:
    from ..cli_credentials import read_codex_cli_credentials_cached
    cred = read_codex_cli_credentials_cached(ttl_ms=EXTERNAL_CLI_SYNC_TTL_MS)
    if not cred:
        return False
    existing = store.profiles.get(CODEX_CLI_PROFILE_ID)
    if existing and hasattr(existing, "expires"):
        if existing.expires and existing.expires > now + EXTERNAL_CLI_NEAR_EXPIRY_MS:
            return False
    store.profiles[CODEX_CLI_PROFILE_ID] = OAuthCredential(
        provider="openai-codex", access=cred.access,
        refresh=cred.refresh, expires=cred.expires,
    )
    return True


def _sync_qwen_cli(store: AuthProfileStore, now: float) -> bool:
    from ..cli_credentials import read_qwen_cli_credentials_cached
    cred = read_qwen_cli_credentials_cached(ttl_ms=EXTERNAL_CLI_SYNC_TTL_MS)
    if not cred:
        return False
    existing = store.profiles.get(QWEN_CLI_PROFILE_ID)
    if existing and hasattr(existing, "expires"):
        if existing.expires and existing.expires > now + EXTERNAL_CLI_NEAR_EXPIRY_MS:
            return False
    store.profiles[QWEN_CLI_PROFILE_ID] = OAuthCredential(
        provider="qwen-portal", access=cred.access,
        refresh=cred.refresh, expires=cred.expires,
    )
    return True


def _sync_minimax_cli(store: AuthProfileStore, now: float) -> bool:
    from ..cli_credentials import read_minimax_cli_credentials_cached
    cred = read_minimax_cli_credentials_cached(ttl_ms=EXTERNAL_CLI_SYNC_TTL_MS)
    if not cred:
        return False
    existing = store.profiles.get(MINIMAX_CLI_PROFILE_ID)
    if existing and hasattr(existing, "expires"):
        if existing.expires and existing.expires > now + EXTERNAL_CLI_NEAR_EXPIRY_MS:
            return False
    store.profiles[MINIMAX_CLI_PROFILE_ID] = OAuthCredential(
        provider="minimax-portal", access=cred.access,
        refresh=cred.refresh, expires=cred.expires,
    )
    return True
