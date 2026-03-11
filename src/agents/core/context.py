"""Context window management — ported from bk/src/agents/context.ts + context-window-guard.ts.

Manages context window token budgets, model-specific limits, and guard evaluation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

log = logging.getLogger("openclaw.agents.context")

# ── Constants ──────────────────────────────────────────────────────────────
CONTEXT_WINDOW_HARD_MIN_TOKENS = 16_000
CONTEXT_WINDOW_WARN_BELOW_TOKENS = 32_000
ANTHROPIC_CONTEXT_1M_TOKENS = 1_048_576
ANTHROPIC_1M_MODEL_PREFIXES = ("claude-opus-4", "claude-sonnet-4")

ContextWindowSource = Literal["model", "modelsConfig", "agentContextTokens", "default"]


# ── Types ──────────────────────────────────────────────────────────────────
@dataclass
class ContextWindowInfo:
    tokens: int
    source: ContextWindowSource


@dataclass
class ContextWindowGuardResult:
    tokens: int
    source: ContextWindowSource
    should_warn: bool
    should_block: bool


# ── Context window cache ──────────────────────────────────────────────────
_MODEL_CACHE: dict[str, int] = {}


def apply_discovered_context_windows(
    cache: dict[str, int],
    models: list[dict[str, Any]],
) -> None:
    """Populate cache from discovered model entries (prefer smaller window when duplicated)."""
    for model in models:
        model_id = model.get("id")
        if not model_id or not isinstance(model_id, str):
            continue
        cw = model.get("contextWindow")
        if not isinstance(cw, (int, float)) or cw <= 0:
            continue
        context_window = int(cw)
        existing = cache.get(model_id)
        if existing is None or context_window < existing:
            cache[model_id] = context_window


def apply_configured_context_windows(
    cache: dict[str, int],
    models_config: dict[str, Any] | None,
) -> None:
    """Populate cache from config file provider/model entries."""
    if not models_config or not isinstance(models_config, dict):
        return
    providers = models_config.get("providers")
    if not providers or not isinstance(providers, dict):
        return
    for provider in providers.values():
        if not isinstance(provider, dict):
            continue
        model_list = provider.get("models")
        if not isinstance(model_list, list):
            continue
        for model in model_list:
            if not isinstance(model, dict):
                continue
            model_id = model.get("id")
            if not isinstance(model_id, str) or not model_id:
                continue
            cw = model.get("contextWindow")
            if not isinstance(cw, (int, float)) or cw <= 0:
                continue
            cache[model_id] = int(cw)


def prime_configured_context_windows(
    config: dict[str, Any] | None = None,
) -> None:
    """Prime the global cache from configuration."""
    if config is None:
        return
    models_config = config.get("models")
    apply_configured_context_windows(_MODEL_CACHE, models_config)


def lookup_context_tokens(model_id: str | None) -> int | None:
    """Look up cached context token limit for a model."""
    if not model_id:
        return None
    return _MODEL_CACHE.get(model_id)


def clear_context_window_cache() -> None:
    """Clear the context window cache (for testing)."""
    _MODEL_CACHE.clear()


# ── Anthropic 1M detection ────────────────────────────────────────────────

def _is_anthropic_1m_model(provider: str, model: str) -> bool:
    if provider != "anthropic":
        return False
    normalized = model.strip().lower()
    model_id = normalized.split("/")[-1] if "/" in normalized else normalized
    return any(model_id.startswith(prefix) for prefix in ANTHROPIC_1M_MODEL_PREFIXES)


# ── Provider/model ref resolution ─────────────────────────────────────────

def _resolve_provider_model_ref(
    provider: str | None,
    model: str | None,
) -> tuple[str, str] | None:
    model_raw = (model or "").strip()
    if not model_raw:
        return None
    provider_raw = (provider or "").strip()
    if provider_raw:
        return provider_raw.lower(), model_raw
    slash = model_raw.find("/")
    if slash <= 0:
        return None
    p = model_raw[:slash].strip().lower()
    m = model_raw[slash + 1:].strip()
    if not p or not m:
        return None
    return p, m


# ── Context window resolution ─────────────────────────────────────────────

def resolve_context_tokens_for_model(
    *,
    cfg: dict[str, Any] | None = None,
    provider: str | None = None,
    model: str | None = None,
    context_tokens_override: int | None = None,
    fallback_context_tokens: int | None = None,
) -> int | None:
    """Resolve the effective context window for a provider/model combination."""
    if isinstance(context_tokens_override, int) and context_tokens_override > 0:
        return context_tokens_override

    ref = _resolve_provider_model_ref(provider, model)
    if ref and cfg:
        p, m = ref
        # Check config for context1m=true on Anthropic models
        models_cfg = cfg.get("agents", {}).get("defaults", {}).get("models", {})
        if isinstance(models_cfg, dict):
            key = f"{p}/{m}".strip().lower()
            for raw_key, entry in models_cfg.items():
                if raw_key.strip().lower() == key:
                    if isinstance(entry, dict):
                        params = entry.get("params")
                        if isinstance(params, dict) and params.get("context1m") is True:
                            if _is_anthropic_1m_model(p, m):
                                return ANTHROPIC_CONTEXT_1M_TOKENS

    return lookup_context_tokens(model) or fallback_context_tokens


# ── Context window guard ──────────────────────────────────────────────────

def _normalize_positive_int(value: Any) -> int | None:
    if not isinstance(value, (int, float)) or not _is_finite(value):
        return None
    result = int(value)
    return result if result > 0 else None


def _is_finite(value: Any) -> bool:
    try:
        import math
        return math.isfinite(value)
    except (TypeError, ValueError):
        return False


def resolve_context_window_info(
    *,
    cfg: dict[str, Any] | None = None,
    provider: str = "",
    model_id: str = "",
    model_context_window: int | None = None,
    default_tokens: int = 128_000,
) -> ContextWindowInfo:
    """Resolve context window from config/model discovery/defaults."""
    # Check models_config
    from_models_config: int | None = None
    if cfg:
        providers = cfg.get("models", {}).get("providers", {})
        if isinstance(providers, dict):
            provider_entry = providers.get(provider, {})
            if isinstance(provider_entry, dict):
                model_list = provider_entry.get("models", [])
                if isinstance(model_list, list):
                    for m in model_list:
                        if isinstance(m, dict) and m.get("id") == model_id:
                            from_models_config = _normalize_positive_int(m.get("contextWindow"))
                            break

    from_model = _normalize_positive_int(model_context_window)

    if from_models_config:
        base_info = ContextWindowInfo(tokens=from_models_config, source="modelsConfig")
    elif from_model:
        base_info = ContextWindowInfo(tokens=from_model, source="model")
    else:
        base_info = ContextWindowInfo(tokens=int(default_tokens), source="default")

    # Check agent-level cap
    if cfg:
        cap_tokens = _normalize_positive_int(
            cfg.get("agents", {}).get("defaults", {}).get("contextTokens")
        )
        if cap_tokens and cap_tokens < base_info.tokens:
            return ContextWindowInfo(tokens=cap_tokens, source="agentContextTokens")

    return base_info


def evaluate_context_window_guard(
    info: ContextWindowInfo,
    warn_below_tokens: int | None = None,
    hard_min_tokens: int | None = None,
) -> ContextWindowGuardResult:
    """Evaluate whether context window is too small."""
    warn_below = max(1, int(warn_below_tokens or CONTEXT_WINDOW_WARN_BELOW_TOKENS))
    hard_min = max(1, int(hard_min_tokens or CONTEXT_WINDOW_HARD_MIN_TOKENS))
    tokens = max(0, int(info.tokens))
    return ContextWindowGuardResult(
        tokens=tokens,
        source=info.source,
        should_warn=tokens > 0 and tokens < warn_below,
        should_block=tokens > 0 and tokens < hard_min,
    )
