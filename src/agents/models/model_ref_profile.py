"""Model ref profile — ported from bk/src/agents/model-ref-profile.ts."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass
class ModelRefProfile:
    provider: str
    model: str
    profile_id: str | None = None
    base_url: str | None = None

def parse_model_ref_string(ref: str) -> ModelRefProfile | None:
    if not ref or not isinstance(ref, str):
        return None
    trimmed = ref.strip()
    if not trimmed:
        return None
    parts = trimmed.split("/", 1)
    if len(parts) == 2:
        provider = parts[0].strip().lower()
        model = parts[1].strip()
        return ModelRefProfile(provider=provider, model=model) if provider and model else None
    return ModelRefProfile(provider="", model=trimmed)

def format_model_ref(ref: ModelRefProfile) -> str:
    if ref.provider:
        display = f"{ref.provider}/{ref.model}"
    else:
        display = ref.model
    if ref.profile_id:
        display += f" [{ref.profile_id}]"
    return display
