"""Model catalog — ported from bk/src/agents/model-catalog.ts.

Provides model discovery, catalog management, and capability queries
(vision support, document support, reasoning).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

log = logging.getLogger("openclaw.models.catalog")

ModelInputType = Literal["text", "image", "document"]


@dataclass
class ModelCatalogEntry:
    id: str
    name: str
    provider: str
    context_window: int | None = None
    reasoning: bool | None = None
    input: list[ModelInputType] | None = None


# ── Cache ──────────────────────────────────────────────────────────────────
_catalog_cache: list[ModelCatalogEntry] | None = None
_has_logged_error = False


def reset_model_catalog_cache() -> None:
    """Reset the cached catalog (for testing)."""
    global _catalog_cache, _has_logged_error
    _catalog_cache = None
    _has_logged_error = False


# ── Synthetic fallbacks ───────────────────────────────────────────────────

@dataclass(frozen=True)
class _SyntheticFallback:
    provider: str
    id: str
    template_ids: tuple[str, ...]


_SYNTHETIC_FALLBACKS: list[_SyntheticFallback] = [
    _SyntheticFallback("openai", "gpt-5.4", ("gpt-5.2",)),
    _SyntheticFallback("openai", "gpt-5.4-pro", ("gpt-5.2-pro", "gpt-5.2")),
    _SyntheticFallback("openai-codex", "gpt-5.4", ("gpt-5.3-codex", "gpt-5.2-codex")),
    _SyntheticFallback("openai-codex", "gpt-5.3-codex-spark", ("gpt-5.3-codex",)),
]

NON_PI_NATIVE_MODEL_PROVIDERS: set[str] = {"kilocode"}


def _apply_synthetic_fallbacks(models: list[ModelCatalogEntry]) -> None:
    """Add synthetic entries for models that should inherit from templates."""

    def _find(provider: str, model_id: str) -> ModelCatalogEntry | None:
        p_lower = provider.lower()
        m_lower = model_id.lower()
        for entry in models:
            if entry.provider.lower() == p_lower and entry.id.lower() == m_lower:
                return entry
        return None

    for fb in _SYNTHETIC_FALLBACKS:
        if _find(fb.provider, fb.id):
            continue
        template: ModelCatalogEntry | None = None
        for tid in fb.template_ids:
            template = _find(fb.provider, tid)
            if template:
                break
        if not template:
            continue
        models.append(ModelCatalogEntry(
            id=fb.id,
            name=fb.id,
            provider=template.provider,
            context_window=template.context_window,
            reasoning=template.reasoning,
            input=list(template.input) if template.input else None,
        ))


# ── Config-driven model loading ──────────────────────────────────────────

def _normalize_model_input(raw: Any) -> list[ModelInputType] | None:
    if not isinstance(raw, list):
        return None
    valid: list[ModelInputType] = []
    for item in raw:
        if item in ("text", "image", "document"):
            valid.append(item)
    return valid or None


def _read_config_opt_in_models(config: dict[str, Any]) -> list[ModelCatalogEntry]:
    """Read models from non-Pi-native providers configured in config."""
    providers = config.get("models", {}).get("providers", {})
    if not isinstance(providers, dict):
        return []

    out: list[ModelCatalogEntry] = []
    for provider_raw, provider_value in providers.items():
        provider = provider_raw.lower().strip()
        if provider not in NON_PI_NATIVE_MODEL_PROVIDERS:
            continue
        if not isinstance(provider_value, dict):
            continue
        configured_models = provider_value.get("models")
        if not isinstance(configured_models, list):
            continue

        for cm in configured_models:
            if not isinstance(cm, dict):
                continue
            id_raw = cm.get("id")
            if not isinstance(id_raw, str):
                continue
            model_id = id_raw.strip()
            if not model_id:
                continue
            name_raw = cm.get("name")
            name = (name_raw if isinstance(name_raw, str) else model_id).strip() or model_id
            cw = cm.get("contextWindow")
            context_window = int(cw) if isinstance(cw, (int, float)) and cw > 0 else None
            reasoning_raw = cm.get("reasoning")
            reasoning = reasoning_raw if isinstance(reasoning_raw, bool) else None
            model_input = _normalize_model_input(cm.get("input"))
            out.append(ModelCatalogEntry(
                id=model_id,
                name=name,
                provider=provider,
                context_window=context_window,
                reasoning=reasoning,
                input=model_input,
            ))
    return out


def _merge_config_opt_in_models(
    config: dict[str, Any],
    models: list[ModelCatalogEntry],
) -> None:
    configured = _read_config_opt_in_models(config)
    if not configured:
        return
    seen = {
        f"{e.provider.lower().strip()}::{e.id.lower().strip()}"
        for e in models
    }
    for entry in configured:
        key = f"{entry.provider.lower().strip()}::{entry.id.lower().strip()}"
        if key in seen:
            continue
        models.append(entry)
        seen.add(key)


# ── Public API ─────────────────────────────────────────────────────────────

def load_model_catalog(
    config: dict[str, Any] | None = None,
    use_cache: bool = True,
    registered_models: list[dict[str, Any]] | None = None,
) -> list[ModelCatalogEntry]:
    """Load the model catalog from registered models and config.

    Args:
        config: OpenClaw config dict.
        use_cache: Whether to use the cached result.
        registered_models: Pre-discovered model entries (from a model registry).

    Returns:
        Sorted list of ModelCatalogEntry.
    """
    global _catalog_cache, _has_logged_error

    if not use_cache:
        _catalog_cache = None
    if _catalog_cache is not None:
        return _catalog_cache

    models: list[ModelCatalogEntry] = []

    try:
        # Load from pre-discovered entries
        if registered_models:
            for entry in registered_models:
                if not isinstance(entry, dict):
                    continue
                model_id = str(entry.get("id", "")).strip()
                if not model_id:
                    continue
                provider = str(entry.get("provider", "")).strip()
                if not provider:
                    continue
                name = str(entry.get("name", model_id)).strip() or model_id
                cw = entry.get("contextWindow")
                context_window = int(cw) if isinstance(cw, (int, float)) and cw > 0 else None
                reasoning_raw = entry.get("reasoning")
                reasoning = reasoning_raw if isinstance(reasoning_raw, bool) else None
                model_input = _normalize_model_input(entry.get("input"))
                models.append(ModelCatalogEntry(
                    id=model_id,
                    name=name,
                    provider=provider,
                    context_window=context_window,
                    reasoning=reasoning,
                    input=model_input,
                ))

        # Merge config-driven opt-in provider models
        if config:
            _merge_config_opt_in_models(config, models)

        # Apply synthetic fallbacks
        _apply_synthetic_fallbacks(models)

        # Sort by provider, then name
        models.sort(key=lambda e: (e.provider.lower(), e.name.lower()))

        if models:
            _catalog_cache = models

    except Exception as exc:
        if not _has_logged_error:
            _has_logged_error = True
            log.warning("Failed to load model catalog: %s", exc)
        _catalog_cache = None

    return models


def model_supports_vision(entry: ModelCatalogEntry | None) -> bool:
    """Check if a model supports image input."""
    if entry is None or entry.input is None:
        return False
    return "image" in entry.input


def model_supports_document(entry: ModelCatalogEntry | None) -> bool:
    """Check if a model supports native document/PDF input."""
    if entry is None or entry.input is None:
        return False
    return "document" in entry.input


def find_model_in_catalog(
    catalog: list[ModelCatalogEntry],
    provider: str,
    model_id: str,
) -> ModelCatalogEntry | None:
    """Find a model in the catalog by provider and model ID."""
    p = provider.lower().strip()
    m = model_id.lower().strip()
    for entry in catalog:
        if entry.provider.lower() == p and entry.id.lower() == m:
            return entry
    return None
