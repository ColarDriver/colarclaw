"""Auth profile credential state — ported from bk/src/agents/auth-profiles/credential-state.ts."""
from __future__ import annotations

import time
from typing import Any, Literal

from .types import AuthProfileCredential

AuthCredentialReasonCode = Literal["ok", "missing_credential", "invalid_expires", "expired", "unresolved_ref"]
TokenExpiryState = Literal["missing", "valid", "expired", "invalid_expires"]


def resolve_token_expiry_state(expires: Any, now: float | None = None) -> TokenExpiryState:
    if now is None:
        now = time.time() * 1000
    if expires is None:
        return "missing"
    if not isinstance(expires, (int, float)):
        return "invalid_expires"
    if expires <= 0 or not (expires == expires):  # NaN check
        return "invalid_expires"
    return "expired" if now >= expires else "valid"


def evaluate_stored_credential_eligibility(
    credential: AuthProfileCredential,
    now: float | None = None,
) -> dict[str, Any]:
    """Check if a stored credential is eligible for use."""
    if now is None:
        now = time.time() * 1000

    if hasattr(credential, "type") and credential.type == "api_key":
        has_key = bool(getattr(credential, "key", None))
        has_ref = bool(getattr(credential, "key_ref", None))
        if not has_key and not has_ref:
            return {"eligible": False, "reason_code": "missing_credential"}
        return {"eligible": True, "reason_code": "ok"}

    if hasattr(credential, "type") and credential.type == "token":
        has_token = bool(getattr(credential, "token", None))
        has_ref = bool(getattr(credential, "token_ref", None))
        if not has_token and not has_ref:
            return {"eligible": False, "reason_code": "missing_credential"}
        expiry_state = resolve_token_expiry_state(getattr(credential, "expires", None), now)
        if expiry_state == "invalid_expires":
            return {"eligible": False, "reason_code": "invalid_expires"}
        if expiry_state == "expired":
            return {"eligible": False, "reason_code": "expired"}
        return {"eligible": True, "reason_code": "ok"}

    # OAuth
    has_access = bool(getattr(credential, "access", None))
    has_refresh = bool(getattr(credential, "refresh", None))
    if not has_access and not has_refresh:
        return {"eligible": False, "reason_code": "missing_credential"}
    return {"eligible": True, "reason_code": "ok"}
