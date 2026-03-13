"""Qwen Portal OAuth — ported from bk/src/providers/qwen-portal-oauth.ts.

OAuth refresh flow for Qwen Portal provider.
"""
from __future__ import annotations

import time
from typing import Any

import httpx

QWEN_OAUTH_BASE_URL = "https://chat.qwen.ai"
QWEN_OAUTH_TOKEN_ENDPOINT = f"{QWEN_OAUTH_BASE_URL}/api/v1/oauth2/token"
QWEN_OAUTH_CLIENT_ID = "f0304373b74a44d2b584a3fb70ca9e56"


async def refresh_qwen_portal_credentials(
    credentials: dict[str, Any],
) -> dict[str, Any]:
    """Refresh Qwen Portal OAuth credentials.

    Returns updated credentials dict with new access/refresh tokens.
    """
    refresh_token = (credentials.get("refresh") or "").strip()
    if not refresh_token:
        raise RuntimeError("Qwen OAuth refresh token missing; re-authenticate.")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            QWEN_OAUTH_TOKEN_ENDPOINT,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": QWEN_OAUTH_CLIENT_ID,
            },
        )

    if response.status_code == 400:
        raise RuntimeError(
            "Qwen OAuth refresh token expired or invalid. "
            "Re-authenticate with `openclaw models auth login --provider qwen-portal`."
        )
    if response.status_code != 200:
        text = response.text
        raise RuntimeError(f"Qwen OAuth refresh failed: {text or response.reason_phrase}")

    payload = response.json()
    access_token = (payload.get("access_token") or "").strip()
    new_refresh_token = (payload.get("refresh_token") or "").strip()
    expires_in = payload.get("expires_in")

    if not access_token:
        raise RuntimeError("Qwen OAuth refresh response missing access token.")
    if not isinstance(expires_in, (int, float)) or expires_in <= 0:
        raise RuntimeError("Qwen OAuth refresh response missing or invalid expires_in.")

    return {
        **credentials,
        "access": access_token,
        "refresh": new_refresh_token or refresh_token,
        "expires": int(time.time() * 1000) + int(expires_in) * 1000,
    }
