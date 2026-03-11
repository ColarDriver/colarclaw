"""Models config merge shard.

Ported from ``bk/src/agents/models-config.merge.ts``.
Implements provider/model merge semantics and secret-preserving merge helpers.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from agents.models_config_providers import (
    ExistingProviderConfig,
    ProviderConfig,
    is_non_secret_api_key_marker,
)


def is_positive_finite_token_limit(value: Any) -> bool:
    """Return True when value is a positive finite token limit number."""
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return False
    return value > 0


def resolve_preferred_token_limit(
    *,
    explicit_present: bool,
    explicit_value: Any,
    implicit_value: Any,
) -> int | float | None:
    """Resolve preferred token limit using TS shard precedence rules."""
    if explicit_present and is_positive_finite_token_limit(explicit_value):
        return explicit_value
    if is_positive_finite_token_limit(implicit_value):
        return implicit_value
    if is_positive_finite_token_limit(explicit_value):
        return explicit_value
    return None


def get_provider_model_id(model: Any) -> str:
    """Extract trimmed model id from a provider model object."""
    if not isinstance(model, Mapping):
        return ""
    model_id = model.get("id")
    return model_id.strip() if isinstance(model_id, str) else ""


def merge_provider_models(
    implicit: ProviderConfig,
    explicit: ProviderConfig,
) -> ProviderConfig:
    """Merge provider entries, preferring explicit while preserving implicit model metadata."""
    implicit_models_raw = implicit.get("models")
    explicit_models_raw = explicit.get("models")
    implicit_models = implicit_models_raw if isinstance(implicit_models_raw, list) else []
    explicit_models = explicit_models_raw if isinstance(explicit_models_raw, list) else []

    if len(implicit_models) == 0:
        merged_empty: ProviderConfig = dict(implicit)
        merged_empty.update(explicit)
        return merged_empty

    implicit_by_id: dict[str, Any] = {}
    for model in implicit_models:
        model_id = get_provider_model_id(model)
        if model_id:
            implicit_by_id[model_id] = model

    seen: set[str] = set()
    merged_models: list[Any] = []

    for explicit_model in explicit_models:
        model_id = get_provider_model_id(explicit_model)
        if not model_id:
            merged_models.append(explicit_model)
            continue

        seen.add(model_id)
        implicit_model = implicit_by_id.get(model_id)
        if not isinstance(implicit_model, Mapping) or not isinstance(explicit_model, Mapping):
            merged_models.append(explicit_model)
            continue

        context_window = resolve_preferred_token_limit(
            explicit_present="contextWindow" in explicit_model,
            explicit_value=explicit_model.get("contextWindow"),
            implicit_value=implicit_model.get("contextWindow"),
        )
        max_tokens = resolve_preferred_token_limit(
            explicit_present="maxTokens" in explicit_model,
            explicit_value=explicit_model.get("maxTokens"),
            implicit_value=implicit_model.get("maxTokens"),
        )

        merged_model = dict(explicit_model)
        merged_model["input"] = implicit_model.get("input")
        if "reasoning" not in explicit_model:
            merged_model["reasoning"] = implicit_model.get("reasoning")
        if context_window is not None:
            merged_model["contextWindow"] = context_window
        if max_tokens is not None:
            merged_model["maxTokens"] = max_tokens
        merged_models.append(merged_model)

    for implicit_model in implicit_models:
        model_id = get_provider_model_id(implicit_model)
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        merged_models.append(implicit_model)

    merged: ProviderConfig = dict(implicit)
    merged.update(explicit)
    merged["models"] = merged_models
    return merged


def merge_providers(
    *,
    implicit: Mapping[str, ProviderConfig] | None = None,
    explicit: Mapping[str, ProviderConfig] | None = None,
) -> dict[str, ProviderConfig]:
    """Merge implicit and explicit provider maps using provider-model merge rules."""
    out: dict[str, ProviderConfig] = dict(implicit or {})

    for key, explicit_entry in (explicit or {}).items():
        provider_key = key.strip()
        if not provider_key:
            continue
        implicit_entry = out.get(provider_key)
        if implicit_entry is None:
            out[provider_key] = explicit_entry
        else:
            out[provider_key] = merge_provider_models(implicit_entry, explicit_entry)
    return out


def resolve_provider_api(entry: Mapping[str, Any] | None) -> str | None:
    """Resolve provider-level API surface identifier."""
    if not entry:
        return None
    api = entry.get("api")
    if not isinstance(api, str):
        return None
    trimmed = api.strip()
    return trimmed or None


def resolve_model_api_surface(entry: Mapping[str, Any] | None) -> str | None:
    """Resolve API surface marker from model-level `api` fields."""
    if not entry:
        return None
    models = entry.get("models")
    if not isinstance(models, list):
        return None

    apis: list[str] = []
    for model in models:
        if not isinstance(model, Mapping):
            continue
        api = model.get("api")
        if isinstance(api, str):
            trimmed = api.strip()
            if trimmed:
                apis.append(trimmed)

    if not apis:
        return None
    apis.sort()
    return json.dumps(apis, separators=(",", ":"))


def resolve_provider_api_surface(entry: Mapping[str, Any] | None) -> str | None:
    """Resolve canonical API surface marker for baseUrl preservation checks."""
    return resolve_provider_api(entry) or resolve_model_api_surface(entry)


def should_preserve_existing_api_key(
    *,
    provider_key: str,
    existing: ExistingProviderConfig,
    secret_ref_managed_providers: set[str],
) -> bool:
    """Return True when existing plaintext api key should be preserved."""
    api_key = existing.get("apiKey")
    return (
        provider_key not in secret_ref_managed_providers
        and isinstance(api_key, str)
        and len(api_key) > 0
        and not is_non_secret_api_key_marker(api_key, include_env_var_name=False)
    )


def should_preserve_existing_base_url(
    *,
    provider_key: str,
    existing: ExistingProviderConfig,
    next_entry: ProviderConfig,
    explicit_base_url_providers: set[str],
) -> bool:
    """Return True when existing baseUrl should be preserved in merge mode."""
    base_url = existing.get("baseUrl")
    if (
        provider_key in explicit_base_url_providers
        or not isinstance(base_url, str)
        or len(base_url) == 0
    ):
        return False

    existing_api = resolve_provider_api_surface(existing)
    next_api = resolve_provider_api_surface(next_entry)
    return (not existing_api) or (not next_api) or (existing_api == next_api)


def merge_with_existing_provider_secrets(
    *,
    next_providers: Mapping[str, ProviderConfig],
    existing_providers: Mapping[str, ExistingProviderConfig],
    secret_ref_managed_providers: set[str],
    explicit_base_url_providers: set[str],
) -> dict[str, ProviderConfig]:
    """Merge generated providers with existing persisted provider secrets/base URLs."""
    merged: dict[str, ProviderConfig] = {
        key: dict(value) for key, value in existing_providers.items()
    }

    for key, new_entry in next_providers.items():
        existing = existing_providers.get(key)
        if existing is None:
            merged[key] = new_entry
            continue

        preserved: dict[str, Any] = {}
        if should_preserve_existing_api_key(
            provider_key=key,
            existing=existing,
            secret_ref_managed_providers=secret_ref_managed_providers,
        ):
            preserved["apiKey"] = existing.get("apiKey")

        if should_preserve_existing_base_url(
            provider_key=key,
            existing=existing,
            next_entry=new_entry,
            explicit_base_url_providers=explicit_base_url_providers,
        ):
            preserved["baseUrl"] = existing.get("baseUrl")

        merged_entry: ProviderConfig = dict(new_entry)
        merged_entry.update(preserved)
        merged[key] = merged_entry

    return merged


__all__ = [
    "is_positive_finite_token_limit",
    "resolve_preferred_token_limit",
    "get_provider_model_id",
    "merge_provider_models",
    "merge_providers",
    "resolve_provider_api",
    "resolve_model_api_surface",
    "resolve_provider_api_surface",
    "should_preserve_existing_api_key",
    "should_preserve_existing_base_url",
    "merge_with_existing_provider_secrets",
]
