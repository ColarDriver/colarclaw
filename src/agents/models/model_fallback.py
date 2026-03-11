"""Model fallback execution.

Ported from bk/src/agents/model-fallback.ts

Provides runWithModelFallback() which tries a list of provider/model candidates
in order, catching rate-limit / overload errors and continuing to the next
candidate.  On success it returns the result plus which model won.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Generic, TypeVar

from agents.model_selection import (
    ModelRef,
    model_key,
    normalize_model_ref,
    parse_model_ref,
    resolve_model_ref_from_string,
    ModelAliasIndex,
    DEFAULT_PROVIDER,
    DEFAULT_MODEL,
)

logger = logging.getLogger("openclaw.agents.model_fallback")

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Error classification helpers
# ---------------------------------------------------------------------------

_RATE_LIMIT_FRAGMENTS = (
    "rate limit",
    "rate_limit",
    "429",
    "too many requests",
    "overloaded",
    "overload",
    "503",
    "service unavailable",
    "capacity",
    "quota",
)

_AUTH_FRAGMENTS = (
    "401",
    "unauthorized",
    "invalid api key",
    "authentication",
    "forbidden",
    "403",
)

_NOT_FOUND_FRAGMENTS = (
    "model not found",
    "no such model",
    "404",
    "does not exist",
)

_CONTEXT_OVERFLOW_FRAGMENTS = (
    "context length",
    "context_length_exceeded",
    "maximum context",
    "too long",
    "input too large",
)


def _err_msg(err: BaseException) -> str:
    return str(err).lower()


def is_rate_limit_error(err: BaseException) -> bool:
    msg = _err_msg(err)
    return any(f in msg for f in _RATE_LIMIT_FRAGMENTS)


def is_auth_error(err: BaseException) -> bool:
    msg = _err_msg(err)
    return any(f in msg for f in _AUTH_FRAGMENTS)


def is_not_found_error(err: BaseException) -> bool:
    msg = _err_msg(err)
    return any(f in msg for f in _NOT_FOUND_FRAGMENTS)


def is_context_overflow_error(err: BaseException) -> bool:
    msg = _err_msg(err)
    return any(f in msg for f in _CONTEXT_OVERFLOW_FRAGMENTS)


def is_fallback_eligible(err: BaseException) -> bool:
    """Return True if the error warrants trying the next model candidate."""
    if isinstance(err, asyncio.CancelledError):
        return False
    if is_context_overflow_error(err):
        return False  # context errors: let inner layer handle compaction/retry
    return is_rate_limit_error(err) or is_auth_error(err) or is_not_found_error(err) or True
    # NOTE: we fall through to True so that any provider error triggers fallback


@dataclass
class FallbackAttempt:
    provider: str
    model: str
    error: str
    reason: str = "unknown"


@dataclass
class ModelFallbackResult(Generic[T]):
    result: T
    provider: str
    model: str
    attempts: list[FallbackAttempt] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Candidate resolution
# ---------------------------------------------------------------------------

def _resolve_fallback_candidates(
    *,
    primary_provider: str,
    primary_model: str,
    fallback_models: list[str],
    default_provider: str = DEFAULT_PROVIDER,
    alias_index: ModelAliasIndex | None = None,
) -> list[ModelRef]:
    """Build ordered list of ModelRef candidates (primary first, then fallbacks)."""
    seen: set[str] = set()
    candidates: list[ModelRef] = []

    def _add(ref: ModelRef) -> None:
        key = ref.key
        if key not in seen:
            seen.add(key)
            candidates.append(ref)

    primary = normalize_model_ref(primary_provider, primary_model)
    _add(primary)

    for raw in fallback_models:
        ref = resolve_model_ref_from_string(
            raw=raw.strip(),
            default_provider=default_provider,
            alias_index=alias_index,
        )
        if ref:
            _add(ref)

    return candidates


# ---------------------------------------------------------------------------
# Main fallback executor
# ---------------------------------------------------------------------------

RunFn = Callable[..., Awaitable[T]]


async def run_with_model_fallback(
    *,
    provider: str,
    model: str,
    fallback_models: list[str],
    run: Callable[[str, str], Awaitable[T]],
    on_error: Callable[[str, str, Exception, int, int], Awaitable[None] | None] | None = None,
    alias_index: ModelAliasIndex | None = None,
    default_provider: str = DEFAULT_PROVIDER,
) -> ModelFallbackResult[T]:
    """Try each model candidate in order; return the first success.

    Args:
        provider: Primary provider key.
        model: Primary model id.
        fallback_models: Ordered list of 'provider/model' fallback strings.
        run: Async callable(provider, model) -> T.
        on_error: Optional async callable called after each failure.
        alias_index: Optional alias index for resolving short model names.
        default_provider: Default provider when none specified in fallback string.

    Returns:
        ModelFallbackResult with result + winning provider/model + attempt log.

    Raises:
        The last error if all candidates fail.
    """
    candidates = _resolve_fallback_candidates(
        primary_provider=provider,
        primary_model=model,
        fallback_models=fallback_models,
        default_provider=default_provider,
        alias_index=alias_index,
    )

    attempts: list[FallbackAttempt] = []
    last_err: Exception | None = None

    for idx, candidate in enumerate(candidates):
        try:
            result = await run(candidate.provider, candidate.model)
            if idx > 0:
                logger.warning(
                    'Fell back to "%s/%s" after %d failure(s)',
                    candidate.provider,
                    candidate.model,
                    idx,
                )
            return ModelFallbackResult(
                result=result,
                provider=candidate.provider,
                model=candidate.model,
                attempts=attempts,
            )
        except asyncio.CancelledError:
            raise
        except Exception as err:
            last_err = err
            if is_context_overflow_error(err):
                raise  # don't try another model for context overflow

            reason = (
                "rate_limit" if is_rate_limit_error(err)
                else "auth" if is_auth_error(err)
                else "model_not_found" if is_not_found_error(err)
                else "unknown"
            )
            attempt = FallbackAttempt(
                provider=candidate.provider,
                model=candidate.model,
                error=str(err),
                reason=reason,
            )
            attempts.append(attempt)

            logger.warning(
                'Model "%s/%s" failed (%s): %s',
                candidate.provider,
                candidate.model,
                reason,
                str(err)[:200],
            )

            if on_error:
                result_or_coro = on_error(candidate.provider, candidate.model, err, idx + 1, len(candidates))
                if asyncio.isfuture(result_or_coro) or asyncio.iscoroutine(result_or_coro):
                    await result_or_coro  # type: ignore[misc]

            # Only continue if fallback is eligible
            if not is_fallback_eligible(err):
                break

    # All candidates exhausted
    if len(attempts) <= 1 and last_err:
        raise last_err

    summary = " | ".join(
        f"{a.provider}/{a.model}: {a.error} ({a.reason})"
        for a in attempts
    )
    raise RuntimeError(
        f"All {len(candidates)} model(s) failed: {summary}",
        # attach cause for tracebacks
    ) from last_err
