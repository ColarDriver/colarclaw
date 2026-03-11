"""Model cache params — ported from bk/src/agents/model-cache-params.ts.

Resolution of model-specific caching parameters (prompt caching,
cache TTL, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .model_selection import normalize_provider_id

DEFAULT_CACHE_TTL_SECONDS = 300


@dataclass
class ModelCacheParams:
    prompt_caching_enabled: bool = False
    cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS
    cache_control_type: str | None = None
    supports_explicit_cache_control: bool = False


# Providers/APIs that support prompt caching
_CACHE_CAPABLE_PROVIDERS = {"anthropic", "google", "deepseek"}
_CACHE_CAPABLE_APIS = {"anthropic-messages", "google-genai", "vertex-ai"}


def resolve_model_cache_params(
    provider: str | None = None,
    model_api: str | None = None,
    model_id: str | None = None,
    config: dict[str, Any] | None = None,
) -> ModelCacheParams:
    """Resolve caching parameters for a model/provider combination."""
    norm_provider = normalize_provider_id(provider or "")

    # Check if provider/API supports caching
    supports_caching = (
        norm_provider in _CACHE_CAPABLE_PROVIDERS
        or (model_api or "") in _CACHE_CAPABLE_APIS
    )

    if not supports_caching:
        return ModelCacheParams()

    # Anthropic-specific cache control
    is_anthropic = norm_provider == "anthropic" or model_api == "anthropic-messages"
    supports_explicit = is_anthropic

    cache_ttl = DEFAULT_CACHE_TTL_SECONDS
    if config:
        custom_ttl = config.get("cacheTtlSeconds") or config.get("cache_ttl_seconds")
        if isinstance(custom_ttl, (int, float)) and custom_ttl > 0:
            cache_ttl = int(custom_ttl)

    cache_control_type = "ephemeral" if is_anthropic else None

    return ModelCacheParams(
        prompt_caching_enabled=True,
        cache_ttl_seconds=cache_ttl,
        cache_control_type=cache_control_type,
        supports_explicit_cache_control=supports_explicit,
    )
