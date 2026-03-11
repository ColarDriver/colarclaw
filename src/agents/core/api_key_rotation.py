"""API key rotation — ported from bk/src/agents/api-key-rotation.ts.

Provides API key deduplication and rotation with automatic retry
on rate-limit errors across multiple keys for a provider.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

log = logging.getLogger("openclaw.agents.api_key_rotation")


def _dedupe_api_keys(raw: list[str]) -> list[str]:
    """Deduplicate API keys preserving order, stripping whitespace."""
    seen: set[str] = set()
    keys: list[str] = []
    for value in raw:
        api_key = value.strip()
        if not api_key or api_key in seen:
            continue
        seen.add(api_key)
        keys.append(api_key)
    return keys


def _is_api_key_rate_limit_error(message: str) -> bool:
    """Heuristic: does the error message suggest a rate-limit or quota issue?"""
    lower = message.lower()
    return any(
        keyword in lower
        for keyword in (
            "rate limit",
            "rate_limit",
            "ratelimit",
            "quota exceeded",
            "too many requests",
            "429",
            "resource_exhausted",
        )
    )


def collect_provider_api_keys_for_execution(
    provider: str,
    primary_api_key: str | None = None,
    additional_keys: list[str] | None = None,
) -> list[str]:
    """Collect and deduplicate API keys for a provider.

    Args:
        provider: Provider name (for logging).
        primary_api_key: The primary API key (highest priority).
        additional_keys: Additional API keys from config/env.

    Returns:
        Deduplicated list of API keys.
    """
    raw = [primary_api_key or ""]
    if additional_keys:
        raw.extend(additional_keys)
    return _dedupe_api_keys(raw)


async def execute_with_api_key_rotation(
    provider: str,
    api_keys: list[str],
    execute: Callable[[str], Awaitable[Any]],
    should_retry: Callable[[str, Exception, int, str], bool] | None = None,
    on_retry: Callable[[str, Exception, int, str], None] | None = None,
) -> Any:
    """Execute an API call with automatic key rotation on rate-limit errors.

    Args:
        provider: Provider name.
        api_keys: List of API keys to try.
        execute: Async function that takes an API key and performs the request.
        should_retry: Optional predicate (api_key, error, attempt, message) -> bool.
        on_retry: Optional callback when retrying with a different key.

    Returns:
        The result of the first successful execution.

    Raises:
        ValueError: If no API keys are configured.
        Exception: The last error if all keys fail.
    """
    keys = _dedupe_api_keys(api_keys)
    if not keys:
        raise ValueError(f'No API keys configured for provider "{provider}".')

    last_error: Exception | None = None

    for attempt, api_key in enumerate(keys):
        try:
            return await execute(api_key)
        except Exception as error:
            last_error = error
            message = str(error)

            retryable = (
                should_retry(api_key, error, attempt, message)
                if should_retry
                else _is_api_key_rate_limit_error(message)
            )

            if not retryable or attempt + 1 >= len(keys):
                break

            if on_retry:
                on_retry(api_key, error, attempt, message)

            log.info(
                "API key rotation: retrying %s (attempt %d/%d) after error: %s",
                provider, attempt + 2, len(keys), message[:200],
            )

    if last_error is None:
        raise RuntimeError(f"Failed to run API request for {provider}.")
    raise last_error
