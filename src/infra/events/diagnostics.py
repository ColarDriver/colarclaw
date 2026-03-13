"""Infra diagnostics — ported from bk/src/infra/diagnostic-events.ts,
diagnostic-flags.ts, unhandled-rejections.ts.

Diagnostic flags, unhandled rejection handling, network error classification.
"""
from __future__ import annotations

import logging
import os
import re
import sys
import traceback
from typing import Any, Callable

logger = logging.getLogger("infra.diagnostics")


# ─── diagnostic-flags.ts ───

DIAGNOSTICS_ENV = "OPENCLAW_DIAGNOSTICS"


def _normalize_flag(value: str) -> str:
    return value.strip().lower()


def _parse_env_flags(raw: str | None) -> list[str]:
    if not raw:
        return []
    trimmed = raw.strip()
    if not trimmed:
        return []
    lowered = trimmed.lower()
    if lowered in ("0", "false", "off", "none"):
        return []
    if lowered in ("1", "true", "all", "*"):
        return ["*"]
    flags = re.split(r"[,\s]+", trimmed)
    return [f for f in (_normalize_flag(f) for f in flags) if f]


def _unique_flags(flags: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for flag in flags:
        normalized = _normalize_flag(flag)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def resolve_diagnostic_flags(
    config_flags: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> list[str]:
    """Resolve diagnostic flags from config and environment."""
    cfg_flags = config_flags or []
    e = env or os.environ
    env_flags = _parse_env_flags(e.get(DIAGNOSTICS_ENV))
    return _unique_flags(cfg_flags + env_flags)


def matches_diagnostic_flag(flag: str, enabled_flags: list[str]) -> bool:
    """Check if a diagnostic flag matches any enabled flag."""
    target = _normalize_flag(flag)
    if not target:
        return False
    for raw in enabled_flags:
        enabled = _normalize_flag(raw)
        if not enabled:
            continue
        if enabled in ("*", "all"):
            return True
        if enabled.endswith(".*"):
            prefix = enabled[:-2]
            if target == prefix or target.startswith(f"{prefix}."):
                return True
        elif enabled.endswith("*"):
            prefix = enabled[:-1]
            if target.startswith(prefix):
                return True
        elif enabled == target:
            return True
    return False


def is_diagnostic_flag_enabled(
    flag: str,
    config_flags: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> bool:
    flags = resolve_diagnostic_flags(config_flags, env)
    return matches_diagnostic_flag(flag, flags)


# ─── unhandled-rejections.ts ───

FATAL_ERROR_CODES = {
    "ERR_OUT_OF_MEMORY",
    "ERR_SCRIPT_EXECUTION_TIMEOUT",
    "ERR_WORKER_OUT_OF_MEMORY",
    "ERR_WORKER_UNCAUGHT_EXCEPTION",
    "ERR_WORKER_INITIALIZATION_FAILED",
}

CONFIG_ERROR_CODES = {"INVALID_CONFIG", "MISSING_API_KEY", "MISSING_CREDENTIALS"}

TRANSIENT_NETWORK_CODES = {
    "ECONNRESET", "ECONNREFUSED", "ENOTFOUND", "ETIMEDOUT",
    "ESOCKETTIMEDOUT", "ECONNABORTED", "EPIPE", "EHOSTUNREACH",
    "ENETUNREACH", "EAI_AGAIN", "EPROTO",
}

TRANSIENT_NETWORK_ERROR_NAMES = {
    "AbortError", "ConnectTimeoutError", "HeadersTimeoutError",
    "BodyTimeoutError", "TimeoutError",
}

_TRANSIENT_MESSAGE_SNIPPETS = [
    "getaddrinfo", "socket hang up",
    "client network socket disconnected",
    "network error", "network is unreachable",
    "temporary failure in name resolution",
    "tlsv1 alert", "ssl routines",
    "connection reset by peer",
]

_unhandled_handlers: list[Callable[[Exception], bool]] = []


def _extract_error_code(err: BaseException) -> str | None:
    if hasattr(err, "errno") and err.errno:
        return str(err.errno).upper()
    return None


def is_abort_error(err: BaseException) -> bool:
    name = type(err).__name__
    if name == "AbortError":
        return True
    msg = str(err).lower()
    if "this operation was aborted" in msg:
        return True
    if isinstance(err, (asyncio_CancelledError(),)):
        return True
    return False


def asyncio_CancelledError():
    import asyncio
    return asyncio.CancelledError


def is_transient_network_error(err: BaseException) -> bool:
    """Check if error is a transient network error."""
    code = _extract_error_code(err)
    if code and code in TRANSIENT_NETWORK_CODES:
        return True
    name = type(err).__name__
    if name in TRANSIENT_NETWORK_ERROR_NAMES:
        return True
    msg = str(err).lower()
    for snippet in _TRANSIENT_MESSAGE_SNIPPETS:
        if snippet in msg:
            return True
    # Check cause chain
    cause = getattr(err, "__cause__", None) or getattr(err, "__context__", None)
    if cause and isinstance(cause, BaseException):
        return is_transient_network_error(cause)
    return False


def is_fatal_error(err: BaseException) -> bool:
    code = _extract_error_code(err)
    return code is not None and code in FATAL_ERROR_CODES


def is_config_error(err: BaseException) -> bool:
    code = _extract_error_code(err)
    return code is not None and code in CONFIG_ERROR_CODES


def format_uncaught_error(err: Any) -> str:
    if isinstance(err, BaseException):
        return "".join(traceback.format_exception(type(err), err, err.__traceback__))
    return str(err)


def register_unhandled_handler(handler: Callable[[Exception], bool]) -> Callable[[], None]:
    _unhandled_handlers.append(handler)
    def dispose():
        try:
            _unhandled_handlers.remove(handler)
        except ValueError:
            pass
    return dispose


def handle_unhandled_exception(err: Exception) -> bool:
    """Try registered handlers; return True if handled."""
    for handler in _unhandled_handlers:
        try:
            if handler(err):
                return True
        except Exception:
            pass
    return False


def install_unhandled_exception_hook() -> None:
    """Install a global exception hook for unhandled exceptions."""
    original = sys.excepthook

    def hook(exc_type, exc_value, exc_tb):
        if handle_unhandled_exception(exc_value):
            return

        if is_abort_error(exc_value):
            logger.warning(f"Suppressed AbortError: {format_uncaught_error(exc_value)}")
            return

        if is_fatal_error(exc_value):
            logger.error(f"FATAL: {format_uncaught_error(exc_value)}")
            sys.exit(1)

        if is_config_error(exc_value):
            logger.error(f"CONFIG ERROR: {format_uncaught_error(exc_value)}")
            sys.exit(1)

        if is_transient_network_error(exc_value):
            logger.warning(f"Transient network error (continuing): {format_uncaught_error(exc_value)}")
            return

        original(exc_type, exc_value, exc_tb)

    sys.excepthook = hook
