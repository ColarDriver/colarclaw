"""Pi embedded runner model — ported from bk/src/agents/pi-embedded-runner/model.ts.

Model resolution for embedded runners: provider config, inline models,
forward-compat fallbacks, and local provider hints.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("openclaw.agents.pi_embedded_runner.model")

DEFAULT_CONTEXT_TOKENS = 128_000

LOCAL_PROVIDER_HINTS: dict[str, str] = {
    "ollama": (
        "Ollama requires authentication to be registered as a provider. "
        'Set OLLAMA_API_KEY="ollama-local" (any value works) or run "openclaw configure". '
        "See: https://docs.openclaw.ai/providers/ollama"
    ),
    "vllm": (
        "vLLM requires authentication to be registered as a provider. "
        'Set VLLM_API_KEY (any value works) or run "openclaw configure". '
        "See: https://docs.openclaw.ai/providers/vllm"
    ),
}


@dataclass
class InlineModelEntry:
    id: str = ""
    name: str = ""
    provider: str = ""
    api: str | None = None
    base_url: str | None = None
    reasoning: bool = False
    input: list[str] = field(default_factory=lambda: ["text"])
    cost: dict[str, float] | None = None
    context_window: int = DEFAULT_CONTEXT_TOKENS
    max_tokens: int = DEFAULT_CONTEXT_TOKENS
    headers: dict[str, str] | None = None
    compat: dict[str, Any] | None = None


def sanitize_model_headers(
    headers: Any,
    strip_secret_ref_markers: bool = False,
) -> dict[str, str] | None:
    if not headers or not isinstance(headers, dict):
        return None
    result = {}
    for key, value in headers.items():
        if not isinstance(value, str):
            continue
        if strip_secret_ref_markers and value.startswith("$ref:"):
            continue
        result[key] = value
    return result if result else None


def build_inline_provider_models(
    providers: dict[str, Any],
) -> list[InlineModelEntry]:
    results: list[InlineModelEntry] = []
    for provider_id, entry in providers.items():
        pid = provider_id.strip()
        if not pid or not isinstance(entry, dict):
            continue
        provider_headers = sanitize_model_headers(entry.get("headers"))
        base_url = entry.get("baseUrl") or entry.get("base_url")
        api = entry.get("api")
        for model in entry.get("models", []):
            if not isinstance(model, dict):
                continue
            model_headers = sanitize_model_headers(model.get("headers"))
            merged_headers = None
            if provider_headers or model_headers:
                merged_headers = {**(provider_headers or {}), **(model_headers or {})}
            results.append(InlineModelEntry(
                id=model.get("id", ""),
                name=model.get("name", model.get("id", "")),
                provider=pid,
                api=model.get("api") or api,
                base_url=base_url,
                reasoning=model.get("reasoning", False),
                input=model.get("input", ["text"]),
                cost=model.get("cost"),
                context_window=model.get("contextWindow", model.get("context_window", DEFAULT_CONTEXT_TOKENS)),
                max_tokens=model.get("maxTokens", model.get("max_tokens", DEFAULT_CONTEXT_TOKENS)),
                headers=merged_headers,
            ))
    return results


def resolve_model_with_registry(
    provider: str,
    model_id: str,
    model_registry: Any = None,
    cfg: Any = None,
) -> dict[str, Any] | None:
    """Resolve a model from the registry, inline config, or forward-compat."""
    from ..model_selection import normalize_provider_id
    normalized = normalize_provider_id(provider)

    # Try registry first
    if model_registry:
        model = None
        if hasattr(model_registry, "find"):
            model = model_registry.find(provider, model_id)
        if model:
            return model

    # Try inline models from config
    if cfg:
        providers = {}
        if hasattr(cfg, "models") and hasattr(cfg.models, "providers"):
            providers = cfg.models.providers or {}
        elif isinstance(cfg, dict):
            providers = cfg.get("models", {}).get("providers", {})
        if providers:
            inline_models = build_inline_provider_models(providers)
            for entry in inline_models:
                if normalize_provider_id(entry.provider) == normalized and entry.id == model_id:
                    return {"id": entry.id, "name": entry.name, "api": entry.api,
                            "provider": entry.provider, "baseUrl": entry.base_url}

    # OpenRouter pass-through
    if normalized == "openrouter":
        return {
            "id": model_id, "name": model_id, "api": "openai-completions",
            "provider": provider, "baseUrl": "https://openrouter.ai/api/v1",
            "reasoning": False, "input": ["text"],
            "contextWindow": DEFAULT_CONTEXT_TOKENS, "maxTokens": 8192,
        }

    return None


def build_unknown_model_error(provider: str, model_id: str) -> str:
    base = f"Unknown model: {provider}/{model_id}"
    hint = LOCAL_PROVIDER_HINTS.get(provider.lower())
    return f"{base}. {hint}" if hint else base
