from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, Header, HTTPException, status
from fastapi.websockets import WebSocket

from core.config import Settings, load_settings

try:
    import jwt
except Exception:  # pragma: no cover - optional dependency fallback
    jwt = None


@dataclass(frozen=True)
class AuthContext:
    subject: str
    scopes: tuple[str, ...]


def _get_settings() -> Settings:
    return load_settings()


def create_access_token(subject: str, settings: Settings, scopes: tuple[str, ...] = ("chat:write",)) -> str:
    if jwt is None:
        return settings.api_token
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "scp": list(scopes),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=30)).timestamp()),
    }
    return str(jwt.encode(payload, settings.jwt_secret, algorithm="HS256"))


def _decode_token(token: str, settings: Settings) -> AuthContext:
    if token == settings.api_token:
        return AuthContext(subject="operator", scopes=("admin", "chat:write", "chat:read", "ws:connect"))
    if jwt is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )
    except Exception as exc:  # pragma: no cover - depends on pyjwt runtime
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token") from exc
    scopes = tuple(payload.get("scp", []))
    subject = str(payload.get("sub", "unknown"))
    return AuthContext(subject=subject, scopes=scopes)


def require_auth(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(_get_settings),
) -> AuthContext:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing token value")
    return _decode_token(token, settings)


def resolve_websocket_auth(websocket: WebSocket, settings: Settings) -> AuthContext:
    auth_header = websocket.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        if token:
            return _decode_token(token, settings)

    query_token = websocket.query_params.get("token")
    if query_token:
        return _decode_token(query_token.strip(), settings)

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing websocket token")
