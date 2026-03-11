"""Models config public API.

Ported from ``bk/src/agents/models-config.ts`` (Python subset).
Keeps backward-compatible dataclass API while wiring shared shard helpers.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from agents.models_config_merge import merge_providers
from agents.models_config_providers import (
    ProviderConfig,
    ProviderConfigMap,
    build_ollama_provider,
    build_vllm_provider,
    normalize_providers,
)

log = logging.getLogger("openclaw.agents.models_config")


@dataclass
class ModelConfigEntry:
    """Legacy lightweight model entry used by older Python modules."""

    provider: str
    model: str
    api_key: str | None = None
    base_url: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelsConfig:
    """Legacy models config view for list-based model entries."""

    entries: list[ModelConfigEntry] = field(default_factory=list)
    default_provider: str = "anthropic"
    default_model: str = "claude-opus-4-6"


def parse_model_config_entry(raw: dict[str, Any]) -> ModelConfigEntry | None:
    """Parse one list-based model entry into the legacy dataclass form."""
    provider = str(raw.get("provider", "")).strip()
    model = str(raw.get("model", "")).strip()
    if not provider or not model:
        return None
    return ModelConfigEntry(
        provider=provider,
        model=model,
        api_key=raw.get("apiKey") if isinstance(raw.get("apiKey"), str) else None,
        base_url=raw.get("baseUrl") if isinstance(raw.get("baseUrl"), str) else None,
        extra={
            k: v
            for k, v in raw.items()
            if k not in ("provider", "model", "apiKey", "baseUrl")
        },
    )


def _resolve_defaults(cfg: dict[str, Any] | None) -> tuple[str, str]:
    defaults = cfg.get("agents", {}).get("defaults", {}) if isinstance(cfg, dict) else {}
    default_provider_raw = defaults.get("provider", "anthropic")
    default_model_raw = defaults.get("model", "claude-opus-4-6")

    default_provider = (
        default_provider_raw.strip()
        if isinstance(default_provider_raw, str) and default_provider_raw.strip()
        else "anthropic"
    )

    default_model: str
    if isinstance(default_model_raw, dict):
        primary = default_model_raw.get("primary", "claude-opus-4-6")
        default_model = primary if isinstance(primary, str) and primary.strip() else "claude-opus-4-6"
    elif isinstance(default_model_raw, str) and default_model_raw.strip():
        default_model = default_model_raw.strip()
    else:
        default_model = "claude-opus-4-6"

    return default_provider, default_model


def load_models_config(cfg: dict[str, Any] | None = None) -> ModelsConfig:
    """Load legacy list-based models config view from raw config dict."""
    if not cfg:
        return ModelsConfig()

    raw_entries = cfg.get("models", {}).get("list", [])
    entries: list[ModelConfigEntry] = []
    if isinstance(raw_entries, list):
        for raw in raw_entries:
            if isinstance(raw, dict):
                entry = parse_model_config_entry(raw)
                if entry:
                    entries.append(entry)

    default_provider, default_model = _resolve_defaults(cfg)
    return ModelsConfig(
        entries=entries,
        default_provider=default_provider,
        default_model=default_model,
    )


def merge_models_config(base: ModelsConfig, override: ModelsConfig) -> ModelsConfig:
    """Merge legacy list-based models config preserving existing semantics."""
    merged_entries = list(base.entries)
    existing_keys = {(entry.provider, entry.model) for entry in merged_entries}
    for entry in override.entries:
        key = (entry.provider, entry.model)
        if key not in existing_keys:
            existing_keys.add(key)
            merged_entries.append(entry)

    return ModelsConfig(
        entries=merged_entries,
        default_provider=override.default_provider or base.default_provider,
        default_model=override.default_model or base.default_model,
    )


def resolve_providers_from_config(cfg: dict[str, Any] | None = None) -> ProviderConfigMap:
    """Resolve provider map from config, normalized via providers shard helpers."""
    if not isinstance(cfg, dict):
        return {}
    providers_raw = cfg.get("models", {}).get("providers", {})
    if not isinstance(providers_raw, dict):
        return {}
    return normalize_providers(providers_raw)


def merge_provider_maps(
    *,
    implicit: dict[str, ProviderConfig] | None = None,
    explicit: dict[str, ProviderConfig] | None = None,
) -> dict[str, ProviderConfig]:
    """Merge provider maps using shard merge logic (explicit overrides implicit)."""
    return merge_providers(implicit=implicit, explicit=explicit)


__all__ = [
    "ModelConfigEntry",
    "ModelsConfig",
    "ProviderConfig",
    "ProviderConfigMap",
    "parse_model_config_entry",
    "load_models_config",
    "merge_models_config",
    "resolve_providers_from_config",
    "merge_provider_maps",
    "normalize_providers",
    "merge_providers",
    "build_ollama_provider",
    "build_vllm_provider",
]
