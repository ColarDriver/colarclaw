"""Failover error handling — ported from bk/src/agents/failover-error.ts.

Provides FailoverError exception class, failover reason classification,
and HTTP status code mapping for model failover scenarios.
"""
from __future__ import annotations
import re
from typing import Any, Literal

FailoverReason = Literal[
    "billing", "rate_limit", "overloaded", "auth", "auth_permanent",
    "timeout", "format", "model_not_found", "session_expired",
    "context_length", "content_filter", "unknown",
]

ABORT_TIMEOUT_RE = re.compile(r"request was aborted|request aborted", re.IGNORECASE)

TIMEOUT_ERROR_PATTERNS = [
    re.compile(r"timed?\s*out", re.IGNORECASE),
    re.compile(r"timeout", re.IGNORECASE),
    re.compile(r"ETIMEDOUT|ESOCKETTIMEDOUT", re.IGNORECASE),
    re.compile(r"deadline exceeded", re.IGNORECASE),
]

NETWORK_ERROR_CODES = frozenset({
    "ETIMEDOUT", "ESOCKETTIMEDOUT", "ECONNRESET", "ECONNABORTED",
    "ECONNREFUSED", "ENETUNREACH", "EHOSTUNREACH", "ENETRESET", "EAI_AGAIN",
})

class FailoverError(Exception):
    def __init__(
        self, message: str, *,
        reason: FailoverReason,
        provider: str | None = None,
        model: str | None = None,
        profile_id: str | None = None,
        status: int | None = None,
        code: str | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message)
        self.reason = reason
        self.provider = provider
        self.model = model
        self.profile_id = profile_id
        self.status = status
        self.code = code
        self.__cause__ = cause

def is_failover_error(err: Any) -> bool:
    return isinstance(err, FailoverError)

def is_timeout_error_message(message: str) -> bool:
    return any(p.search(message) for p in TIMEOUT_ERROR_PATTERNS)

def resolve_failover_status(reason: FailoverReason) -> int | None:
    mapping: dict[str, int] = {
        "billing": 402, "rate_limit": 429, "overloaded": 503,
        "auth": 401, "auth_permanent": 403, "timeout": 408,
        "format": 400, "model_not_found": 404, "session_expired": 410,
    }
    return mapping.get(reason)

def classify_failover_reason_from_http_status(status: int | None, message: str = "") -> FailoverReason | None:
    if status is None:
        return None
    if status == 401:
        return "auth"
    if status == 402:
        return "billing"
    if status == 403:
        return "auth_permanent"
    if status == 404:
        return "model_not_found"
    if status == 408:
        return "timeout"
    if status == 429:
        return "rate_limit"
    if status == 503:
        return "overloaded"
    if status == 400:
        msg_lower = message.lower()
        if "context" in msg_lower and "length" in msg_lower:
            return "context_length"
        return "format"
    return None

def classify_failover_reason(message: str) -> FailoverReason | None:
    lower = message.lower()
    if "rate limit" in lower or "rate_limit" in lower or "429" in lower:
        return "rate_limit"
    if "billing" in lower or "quota" in lower:
        return "billing"
    if "overloaded" in lower or "503" in lower:
        return "overloaded"
    if "unauthorized" in lower or "401" in lower:
        return "auth"
    if "forbidden" in lower or "403" in lower:
        return "auth_permanent"
    if is_timeout_error_message(message):
        return "timeout"
    if "context" in lower and "length" in lower:
        return "context_length"
    if "content filter" in lower or "content_filter" in lower:
        return "content_filter"
    return None

def _get_error_message(err: Any) -> str:
    if isinstance(err, Exception):
        return str(err)
    if isinstance(err, str):
        return err
    return ""

def _get_status_code(err: Any) -> int | None:
    for attr in ("status", "status_code", "statusCode"):
        val = getattr(err, attr, None)
        if isinstance(val, int):
            return val
    return None

def _get_error_code(err: Any) -> str | None:
    code = getattr(err, "code", None)
    if isinstance(code, str) and code.strip():
        return code.strip()
    return None

def resolve_failover_reason_from_error(err: Any) -> FailoverReason | None:
    if is_failover_error(err):
        return err.reason
    status = _get_status_code(err)
    message = _get_error_message(err)
    status_reason = classify_failover_reason_from_http_status(status, message)
    if status_reason:
        return status_reason
    code = (_get_error_code(err) or "").upper()
    if code in NETWORK_ERROR_CODES:
        return "timeout"
    if is_timeout_error_message(message):
        return "timeout"
    if not message:
        return None
    return classify_failover_reason(message)

def describe_failover_error(err: Any) -> dict[str, Any]:
    if is_failover_error(err):
        return {"message": str(err), "reason": err.reason, "status": err.status, "code": err.code}
    message = _get_error_message(err) or str(err)
    return {
        "message": message,
        "reason": resolve_failover_reason_from_error(err),
        "status": _get_status_code(err),
        "code": _get_error_code(err),
    }

def coerce_to_failover_error(
    err: Any, provider: str | None = None, model: str | None = None, profile_id: str | None = None,
) -> FailoverError | None:
    if is_failover_error(err):
        return err
    reason = resolve_failover_reason_from_error(err)
    if not reason:
        return None
    message = _get_error_message(err) or str(err)
    status = _get_status_code(err) or resolve_failover_status(reason)
    code = _get_error_code(err)
    return FailoverError(
        message, reason=reason, provider=provider, model=model,
        profile_id=profile_id, status=status, code=code,
        cause=err if isinstance(err, Exception) else None,
    )
