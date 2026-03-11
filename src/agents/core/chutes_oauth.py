"""Chutes OAuth — ported from bk/src/agents/chutes-oauth.ts.

OAuth helpers for the Chutes AI provider: PKCE, token exchange, refresh, user info.
"""
from __future__ import annotations

import hashlib
import math
import os
import secrets
from dataclasses import dataclass
from typing import Any

CHUTES_OAUTH_ISSUER = "https://api.chutes.ai"
CHUTES_AUTHORIZE_ENDPOINT = f"{CHUTES_OAUTH_ISSUER}/idp/authorize"
CHUTES_TOKEN_ENDPOINT = f"{CHUTES_OAUTH_ISSUER}/idp/token"
CHUTES_USERINFO_ENDPOINT = f"{CHUTES_OAUTH_ISSUER}/idp/userinfo"

DEFAULT_EXPIRES_BUFFER_MS = 5 * 60 * 1000


@dataclass
class ChutesPkce:
    verifier: str
    challenge: str


@dataclass
class ChutesUserInfo:
    sub: str | None = None
    username: str | None = None
    created_at: str | None = None


@dataclass
class ChutesOAuthAppConfig:
    client_id: str
    client_secret: str | None = None
    redirect_uri: str = ""
    scopes: list[str] | None = None


@dataclass
class ChutesStoredOAuth:
    access: str
    refresh: str
    expires: float
    email: str | None = None
    account_id: str | None = None
    client_id: str | None = None


def generate_chutes_pkce() -> ChutesPkce:
    """Generate PKCE verifier and challenge."""
    verifier = secrets.token_hex(32)
    import base64
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return ChutesPkce(verifier=verifier, challenge=challenge)


def parse_oauth_callback_input(
    input_str: str,
    expected_state: str,
) -> dict[str, str]:
    """Parse OAuth callback URL/querystring. Returns dict with 'code' and 'state', or 'error'."""
    trimmed = input_str.strip()
    if not trimmed:
        return {"error": "No input provided"}

    from urllib.parse import urlparse, parse_qs

    parsed_url = None
    try:
        parsed_url = urlparse(trimmed)
        if not parsed_url.scheme:
            raise ValueError("no scheme")
    except Exception:
        # Not a full URL
        has_space = " " in trimmed
        has_scheme = "://" in trimmed
        has_query = "?" in trimmed or "=" in trimmed
        if not has_space and not has_scheme and not has_query:
            return {"error": "Paste the full redirect URL (must include code + state)."}
        qs = trimmed if trimmed.startswith("?") else f"?{trimmed}"
        try:
            parsed_url = urlparse(f"http://localhost/{qs}")
        except Exception:
            return {"error": "Paste the full redirect URL (must include code + state)."}

    if parsed_url is None:
        return {"error": "Paste the full redirect URL (must include code + state)."}

    params = parse_qs(parsed_url.query)
    code = (params.get("code", [None]) or [None])[0]
    state = (params.get("state", [None]) or [None])[0]

    if code:
        code = code.strip()
    if state:
        state = state.strip()

    if not code:
        return {"error": "Missing 'code' parameter in URL"}
    if not state:
        return {"error": "Missing 'state' parameter. Paste the full redirect URL."}
    if state != expected_state:
        return {"error": "OAuth state mismatch - possible CSRF attack. Please retry login."}
    return {"code": code, "state": state}


def _coerce_expires_at(expires_in_seconds: float, now: float) -> float:
    value = now + max(0, math.floor(expires_in_seconds)) * 1000 - DEFAULT_EXPIRES_BUFFER_MS
    return max(value, now + 30_000)


async def fetch_chutes_user_info(
    access_token: str,
    fetch_fn: Any | None = None,
) -> ChutesUserInfo | None:
    """Fetch user info from Chutes."""
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {access_token}"}
            async with session.get(CHUTES_USERINFO_ENDPOINT, headers=headers) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if not data or not isinstance(data, dict):
                    return None
                return ChutesUserInfo(
                    sub=data.get("sub"),
                    username=data.get("username"),
                    created_at=data.get("created_at"),
                )
    except Exception:
        return None


async def exchange_chutes_code_for_tokens(
    app: ChutesOAuthAppConfig,
    code: str,
    code_verifier: str,
    now: float | None = None,
) -> ChutesStoredOAuth:
    """Exchange authorization code for tokens."""
    import aiohttp
    import time
    now_ms = now or (time.time() * 1000)

    body = {
        "grant_type": "authorization_code",
        "client_id": app.client_id,
        "code": code,
        "redirect_uri": app.redirect_uri,
        "code_verifier": code_verifier,
    }
    if app.client_secret:
        body["client_secret"] = app.client_secret

    async with aiohttp.ClientSession() as session:
        async with session.post(
            CHUTES_TOKEN_ENDPOINT,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Chutes token exchange failed: {text}")
            data = await resp.json()

    access = (data.get("access_token") or "").strip()
    refresh = (data.get("refresh_token") or "").strip()
    expires_in = data.get("expires_in", 0)

    if not access:
        raise RuntimeError("Chutes token exchange returned no access_token")
    if not refresh:
        raise RuntimeError("Chutes token exchange returned no refresh_token")

    info = await fetch_chutes_user_info(access)

    return ChutesStoredOAuth(
        access=access,
        refresh=refresh,
        expires=_coerce_expires_at(expires_in, now_ms),
        email=info.username if info else None,
        account_id=info.sub if info else None,
        client_id=app.client_id,
    )


async def refresh_chutes_tokens(
    credential: ChutesStoredOAuth,
    now: float | None = None,
) -> ChutesStoredOAuth:
    """Refresh Chutes OAuth tokens."""
    import aiohttp
    import time
    now_ms = now or (time.time() * 1000)

    refresh_token = (credential.refresh or "").strip()
    if not refresh_token:
        raise RuntimeError("Chutes OAuth credential is missing refresh token")

    client_id = (credential.client_id or "").strip() or os.environ.get("CHUTES_CLIENT_ID", "").strip()
    if not client_id:
        raise RuntimeError(
            "Missing CHUTES_CLIENT_ID for Chutes OAuth refresh (set env var or re-auth)."
        )
    client_secret = os.environ.get("CHUTES_CLIENT_SECRET", "").strip() or None

    body = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": refresh_token,
    }
    if client_secret:
        body["client_secret"] = client_secret

    async with aiohttp.ClientSession() as session:
        async with session.post(
            CHUTES_TOKEN_ENDPOINT,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Chutes token refresh failed: {text}")
            data = await resp.json()

    access = (data.get("access_token") or "").strip()
    new_refresh = (data.get("refresh_token") or "").strip()
    expires_in = data.get("expires_in", 0)

    if not access:
        raise RuntimeError("Chutes token refresh returned no access_token")

    return ChutesStoredOAuth(
        access=access,
        refresh=new_refresh or refresh_token,
        expires=_coerce_expires_at(expires_in, now_ms),
        email=credential.email,
        account_id=credential.account_id,
        client_id=client_id,
    )
