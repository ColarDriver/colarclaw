"""Model auth label — ported from bk/src/agents/model-auth-label.ts."""
from __future__ import annotations
from typing import Any

def resolve_model_auth_label(provider: str, profile_id: str | None = None) -> str:
    base = provider.strip().lower()
    if profile_id:
        return f"{base}:{profile_id.strip()}"
    return base

def format_model_auth_display(provider: str, model: str | None = None, profile_id: str | None = None) -> str:
    label = resolve_model_auth_label(provider, profile_id)
    if model:
        return f"{label} ({model})"
    return label
