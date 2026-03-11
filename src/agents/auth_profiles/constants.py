"""Auth profile constants — ported from bk/src/agents/auth-profiles/constants.ts."""
from __future__ import annotations

import logging

AUTH_STORE_VERSION = 1
AUTH_PROFILE_FILENAME = "auth-profiles.json"
LEGACY_AUTH_FILENAME = "auth.json"

CLAUDE_CLI_PROFILE_ID = "anthropic:claude-cli"
CODEX_CLI_PROFILE_ID = "openai-codex:codex-cli"
QWEN_CLI_PROFILE_ID = "qwen-portal:qwen-cli"
MINIMAX_CLI_PROFILE_ID = "minimax-portal:minimax-cli"

AUTH_STORE_LOCK_RETRIES = 10
AUTH_STORE_LOCK_STALE_MS = 30_000

EXTERNAL_CLI_SYNC_TTL_MS = 15 * 60 * 1000
EXTERNAL_CLI_NEAR_EXPIRY_MS = 10 * 60 * 1000

log = logging.getLogger("openclaw.agents.auth_profiles")
