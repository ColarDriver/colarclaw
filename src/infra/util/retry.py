"""Infra retry policy — ported from bk/src/infra/retry-policy.ts, retry.ts.

Channel-specific retry runners (Discord, Telegram), configurable retry
with backoff, jitter, shouldRetry predicates, and retryAfterMs extraction.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ..errors import format_error_message
from ..process.core import BackoffPolicy, compute_backoff

logger = logging.getLogger("infra.retry_policy")


# ─── retry.ts ───

@dataclass
class RetryConfig:
    attempts: int = 3
    min_delay_ms: int = 500
    max_delay_ms: int = 30_000
    jitter: float = 0.1


@dataclass
class RetryInfo:
    attempt: int = 0
    max_attempts: int = 3
    delay_ms: int = 0
    err: Exception | None = None
    label: str | None = None


def resolve_retry_config(defaults: RetryConfig, overrides: RetryConfig | None = None) -> RetryConfig:
    if not overrides:
        return defaults
    return RetryConfig(
        attempts=overrides.attempts if overrides.attempts else defaults.attempts,
        min_delay_ms=overrides.min_delay_ms if overrides.min_delay_ms else defaults.min_delay_ms,
        max_delay_ms=overrides.max_delay_ms if overrides.max_delay_ms else defaults.max_delay_ms,
        jitter=overrides.jitter if overrides.jitter else defaults.jitter,
    )


async def retry_async_ex(
    fn: Callable[..., Any],
    config: RetryConfig | None = None,
    label: str | None = None,
    should_retry: Callable[[Exception], bool] | None = None,
    retry_after_ms: Callable[[Exception], int | None] | None = None,
    on_retry: Callable[[RetryInfo], None] | None = None,
) -> Any:
    """Advanced retry with shouldRetry/retryAfterMs callbacks."""
    cfg = config or RetryConfig()
    last_error: Exception | None = None

    for attempt in range(1, cfg.attempts + 1):
        try:
            return await fn()
        except Exception as e:
            last_error = e
            if attempt >= cfg.attempts:
                raise
            if should_retry and not should_retry(e):
                raise

            # Compute delay
            after_ms: int | None = None
            if retry_after_ms:
                after_ms = retry_after_ms(e)

            if after_ms and after_ms > 0:
                delay = min(after_ms, cfg.max_delay_ms)
            else:
                backoff = BackoffPolicy(
                    initial_ms=cfg.min_delay_ms,
                    max_ms=cfg.max_delay_ms,
                    jitter=cfg.jitter,
                )
                delay = compute_backoff(backoff, attempt)

            info = RetryInfo(
                attempt=attempt,
                max_attempts=cfg.attempts,
                delay_ms=delay,
                err=e,
                label=label,
            )
            if on_retry:
                on_retry(info)

            await asyncio.sleep(delay / 1000.0)

    raise last_error or RuntimeError("retry exhausted")


# ─── retry-policy.ts: Discord ───

DISCORD_RETRY_DEFAULTS = RetryConfig(
    attempts=3,
    min_delay_ms=500,
    max_delay_ms=30_000,
    jitter=0.1,
)


def _is_discord_rate_limit_error(err: Exception) -> bool:
    """Check if error is a Discord rate limit error."""
    error_name = type(err).__name__
    if "RateLimitError" in error_name or "RateLimit" in error_name:
        return True
    msg = str(err).lower()
    return "rate limit" in msg or "429" in msg


def _get_discord_retry_after_ms(err: Exception) -> int | None:
    """Extract retry-after from Discord rate limit error."""
    retry_after = getattr(err, "retry_after", None) or getattr(err, "retryAfter", None)
    if isinstance(retry_after, (int, float)) and retry_after > 0:
        return int(retry_after * 1000)
    return None


def create_discord_retry_runner(
    retry: RetryConfig | None = None,
    config_retry: RetryConfig | None = None,
    verbose: bool = False,
) -> Callable:
    """Create a Discord-specific retry runner."""
    merged = resolve_retry_config(DISCORD_RETRY_DEFAULTS, config_retry)
    if retry:
        merged = resolve_retry_config(merged, retry)

    async def runner(fn: Callable, label: str | None = None) -> Any:
        return await retry_async_ex(
            fn,
            config=merged,
            label=label,
            should_retry=_is_discord_rate_limit_error,
            retry_after_ms=_get_discord_retry_after_ms,
            on_retry=(
                lambda info: logger.warning(
                    f"discord {info.label or 'request'} rate limited, "
                    f"retry {info.attempt}/{max(1, info.max_attempts - 1)} in {info.delay_ms}ms"
                )
            ) if verbose else None,
        )

    return runner


# ─── retry-policy.ts: Telegram ───

TELEGRAM_RETRY_DEFAULTS = RetryConfig(
    attempts=3,
    min_delay_ms=400,
    max_delay_ms=30_000,
    jitter=0.1,
)

_TELEGRAM_RETRY_RE = re.compile(r"429|timeout|connect|reset|closed|unavailable|temporarily", re.I)


def _resolve_telegram_should_retry(
    should_retry: Callable[[Exception], bool] | None = None,
    strict: bool = False,
) -> Callable[[Exception], bool]:
    if not should_retry:
        return lambda err: bool(_TELEGRAM_RETRY_RE.search(format_error_message(err)))
    if strict:
        return should_retry
    return lambda err: should_retry(err) or bool(_TELEGRAM_RETRY_RE.search(format_error_message(err)))


def _get_telegram_retry_after_ms(err: Exception) -> int | None:
    """Extract retry_after from Telegram-style error objects."""
    for attr in ("parameters", "response", "error"):
        obj = getattr(err, attr, None)
        if obj and isinstance(obj, dict):
            params = obj.get("parameters", obj)
            if isinstance(params, dict):
                retry_after = params.get("retry_after")
                if isinstance(retry_after, (int, float)) and retry_after > 0:
                    return int(retry_after * 1000)
    return None


def create_telegram_retry_runner(
    retry: RetryConfig | None = None,
    config_retry: RetryConfig | None = None,
    verbose: bool = False,
    should_retry: Callable[[Exception], bool] | None = None,
    strict_should_retry: bool = False,
) -> Callable:
    """Create a Telegram-specific retry runner."""
    merged = resolve_retry_config(TELEGRAM_RETRY_DEFAULTS, config_retry)
    if retry:
        merged = resolve_retry_config(merged, retry)

    resolved_should_retry = _resolve_telegram_should_retry(should_retry, strict_should_retry)

    async def runner(fn: Callable, label: str | None = None) -> Any:
        return await retry_async_ex(
            fn,
            config=merged,
            label=label,
            should_retry=resolved_should_retry,
            retry_after_ms=_get_telegram_retry_after_ms,
            on_retry=(
                lambda info: logger.warning(
                    f"telegram send retry {info.attempt}/{max(1, info.max_attempts - 1)} "
                    f"for {info.label or label or 'request'} in {info.delay_ms}ms: "
                    f"{format_error_message(info.err)}"
                )
            ) if verbose else None,
        )

    return runner
