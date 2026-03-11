"""Auto-reply model runtime — ported from bk/src/auto-reply/model-runtime.ts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def format_provider_model_ref(provider_raw: str, model_raw: str) -> str:
    provider = (provider_raw or "").strip()
    model = (model_raw or "").strip()
    if not provider:
        return model
    if not model:
        return provider
    prefix = f"{provider}/"
    if model.lower().startswith(prefix.lower()):
        normalized = model[len(prefix):].strip()
        if normalized:
            return f"{provider}/{normalized}"
    return f"{provider}/{model}"


@dataclass
class ModelRef:
    provider: str = ""
    model: str = ""
    label: str = ""


def _normalize_model_within_provider(provider: str, model_raw: str) -> str:
    model = (model_raw or "").strip()
    if not provider or not model:
        return model
    prefix = f"{provider}/"
    if model.lower().startswith(prefix.lower()):
        without = model[len(prefix):].strip()
        if without:
            return without
    return model


def normalize_model_ref(
    raw_model: str,
    fallback_provider: str,
    parse_embedded_provider: bool = False,
) -> ModelRef:
    trimmed = (raw_model or "").strip()
    slash_index = trimmed.find("/") if parse_embedded_provider else -1
    if slash_index > 0:
        provider = trimmed[:slash_index].strip()
        model = trimmed[slash_index + 1:].strip()
        if provider and model:
            return ModelRef(provider=provider, model=model, label=f"{provider}/{model}")
    provider = (fallback_provider or "").strip()
    deduped = _normalize_model_within_provider(provider, trimmed)
    return ModelRef(
        provider=provider,
        model=deduped or trimmed,
        label=format_provider_model_ref(provider, deduped or trimmed) if provider else trimmed,
    )


def resolve_selected_and_active_model(
    selected_provider: str,
    selected_model: str,
    session_entry: Any = None,
) -> dict[str, Any]:
    selected = normalize_model_ref(selected_model, selected_provider)
    runtime_model = getattr(session_entry, "model", None) if session_entry else None
    runtime_provider = getattr(session_entry, "model_provider", None) if session_entry else None
    if runtime_model and (runtime_model or "").strip():
        active = normalize_model_ref(
            runtime_model.strip(),
            (runtime_provider or "").strip() or selected.provider,
            not bool(runtime_provider),
        )
    else:
        active = selected
    active_differs = active.provider != selected.provider or active.model != selected.model
    return {"selected": selected, "active": active, "active_differs": active_differs}
