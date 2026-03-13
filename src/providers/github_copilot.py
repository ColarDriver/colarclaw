"""GitHub Copilot provider — ported from bk/src/providers/github-copilot-auth.ts,
github-copilot-token.ts, github-copilot-models.ts.

Device-flow auth, API token exchange/caching, and model catalog.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

# ─── constants ───

CLIENT_ID = "Iv1.b507a08c87ecfe98"
DEVICE_CODE_URL = "https://github.com/login/device/code"
ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
COPILOT_TOKEN_URL = "https://api.github.com/copilot_internal/v2/token"
DEFAULT_COPILOT_API_BASE_URL = "https://api.individual.githubcopilot.com"

DEFAULT_CONTEXT_WINDOW = 128_000
DEFAULT_MAX_TOKENS = 8192

DEFAULT_MODEL_IDS = [
    "claude-sonnet-4.6",
    "claude-sonnet-4.5",
    "gpt-4o",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "o1",
    "o1-mini",
    "o3-mini",
]


# ─── model catalog (github-copilot-models.ts) ───

def get_default_copilot_model_ids() -> list[str]:
    return list(DEFAULT_MODEL_IDS)


def build_copilot_model_definition(model_id: str) -> dict[str, Any]:
    """Build a model definition for a Copilot model ID."""
    mid = model_id.strip()
    if not mid:
        raise ValueError("Model id required")
    return {
        "id": mid,
        "name": mid,
        "api": "openai-responses",
        "reasoning": False,
        "input": ["text", "image"],
        "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
        "contextWindow": DEFAULT_CONTEXT_WINDOW,
        "maxTokens": DEFAULT_MAX_TOKENS,
    }


# ─── token exchange (github-copilot-token.ts) ───

@dataclass
class CachedCopilotToken:
    token: str
    expires_at: int  # epoch ms
    updated_at: int  # epoch ms


def derive_copilot_api_base_url_from_token(token: str) -> str | None:
    """Extract the Copilot API base URL from a token's proxy-ep field."""
    trimmed = token.strip()
    if not trimmed:
        return None
    m = re.search(r"(?:^|;)\s*proxy-ep=([^;\s]+)", trimmed, re.IGNORECASE)
    if not m:
        return None
    proxy_ep = m.group(1).strip()
    if not proxy_ep:
        return None
    host = re.sub(r"^https?://", "", proxy_ep)
    host = re.sub(r"^proxy\.", "api.", host, flags=re.IGNORECASE)
    return f"https://{host}" if host else None


def _is_token_usable(token: CachedCopilotToken, now_ms: int | None = None) -> bool:
    now = now_ms or int(time.time() * 1000)
    return (token.expires_at - now) > 5 * 60 * 1000


def _parse_copilot_token_response(data: dict[str, Any]) -> dict[str, Any]:
    token_val = data.get("token")
    expires_at = data.get("expires_at")
    if not isinstance(token_val, str) or not token_val.strip():
        raise ValueError("Copilot token response missing token")

    if isinstance(expires_at, (int, float)):
        expires_at_ms = int(expires_at * 1000) if expires_at < 10_000_000_000 else int(expires_at)
    elif isinstance(expires_at, str) and expires_at.strip():
        parsed = int(expires_at.strip())
        expires_at_ms = parsed * 1000 if parsed < 10_000_000_000 else parsed
    else:
        raise ValueError("Copilot token response missing expires_at")

    return {"token": token_val, "expires_at": expires_at_ms}


async def resolve_copilot_api_token(
    github_token: str,
    cache_path: str | None = None,
) -> dict[str, Any]:
    """Resolve a Copilot API token, using cache if available.

    Returns dict with token, expires_at, source, base_url.
    """
    # Try cache
    if cache_path and os.path.isfile(cache_path):
        try:
            with open(cache_path) as f:
                cached_data = json.load(f)
            cached = CachedCopilotToken(
                token=cached_data["token"],
                expires_at=cached_data["expiresAt"],
                updated_at=cached_data.get("updatedAt", 0),
            )
            if _is_token_usable(cached):
                return {
                    "token": cached.token,
                    "expires_at": cached.expires_at,
                    "source": f"cache:{cache_path}",
                    "base_url": derive_copilot_api_base_url_from_token(cached.token) or DEFAULT_COPILOT_API_BASE_URL,
                }
        except (json.JSONDecodeError, KeyError):
            pass

    # Fetch fresh
    async with httpx.AsyncClient() as client:
        res = await client.get(
            COPILOT_TOKEN_URL,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {github_token}",
            },
        )
    if res.status_code != 200:
        raise RuntimeError(f"Copilot token exchange failed: HTTP {res.status_code}")

    parsed = _parse_copilot_token_response(res.json())
    payload = {
        "token": parsed["token"],
        "expiresAt": parsed["expires_at"],
        "updatedAt": int(time.time() * 1000),
    }

    # Cache
    if cache_path:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(payload, f)

    return {
        "token": payload["token"],
        "expires_at": payload["expiresAt"],
        "source": f"fetched:{COPILOT_TOKEN_URL}",
        "base_url": derive_copilot_api_base_url_from_token(payload["token"]) or DEFAULT_COPILOT_API_BASE_URL,
    }


# ─── device flow auth (github-copilot-auth.ts) ───

async def request_device_code(scope: str = "read:user") -> dict[str, Any]:
    """Request a GitHub device code for Copilot auth."""
    async with httpx.AsyncClient() as client:
        res = await client.post(
            DEVICE_CODE_URL,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"client_id": CLIENT_ID, "scope": scope},
        )
    if res.status_code != 200:
        raise RuntimeError(f"GitHub device code failed: HTTP {res.status_code}")
    data = res.json()
    if not data.get("device_code") or not data.get("user_code"):
        raise RuntimeError("GitHub device code response missing fields")
    return data


async def poll_for_access_token(
    device_code: str,
    interval_s: float = 5.0,
    expires_at_ms: int = 0,
) -> str:
    """Poll GitHub for an access token after device code auth."""
    import asyncio

    async with httpx.AsyncClient() as client:
        while int(time.time() * 1000) < expires_at_ms:
            res = await client.post(
                ACCESS_TOKEN_URL,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "client_id": CLIENT_ID,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
            )
            if res.status_code != 200:
                raise RuntimeError(f"GitHub device token failed: HTTP {res.status_code}")
            data = res.json()
            if "access_token" in data:
                return data["access_token"]
            err = data.get("error", "unknown")
            if err == "authorization_pending":
                await asyncio.sleep(interval_s)
                continue
            if err == "slow_down":
                await asyncio.sleep(interval_s + 2)
                continue
            if err == "expired_token":
                raise RuntimeError("GitHub device code expired; run login again")
            if err == "access_denied":
                raise RuntimeError("GitHub login cancelled")
            raise RuntimeError(f"GitHub device flow error: {err}")
    raise RuntimeError("GitHub device code expired; run login again")
