"""Model profile — ported from bk/src/agents/model-profile.ts.

Model profile definitions and resolution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ModelProfileId = Literal["default", "fast", "reasoning", "coding", "creative"]


@dataclass
class ModelProfile:
    id: ModelProfileId = "default"
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    system_prompt_prefix: str | None = None
    thinking_budget: int | None = None


_DEFAULT_PROFILES: dict[str, ModelProfile] = {
    "default": ModelProfile(id="default"),
    "fast": ModelProfile(id="fast", temperature=0.3, max_tokens=2048),
    "reasoning": ModelProfile(id="reasoning", temperature=1.0, thinking_budget=10000),
    "coding": ModelProfile(id="coding", temperature=0.2),
    "creative": ModelProfile(id="creative", temperature=0.9, top_p=0.95),
}


def resolve_model_profile(
    profile_id: str | None = None,
    config: dict[str, Any] | None = None,
) -> ModelProfile:
    """Resolve a model profile by ID."""
    if not profile_id:
        return ModelProfile()

    profile = _DEFAULT_PROFILES.get(profile_id)
    if profile:
        return profile

    # Check custom profiles in config
    if config:
        custom_profiles = config.get("profiles", {})
        if isinstance(custom_profiles, dict) and profile_id in custom_profiles:
            custom = custom_profiles[profile_id]
            if isinstance(custom, dict):
                return ModelProfile(
                    id=profile_id,  # type: ignore
                    temperature=custom.get("temperature"),
                    top_p=custom.get("topP") or custom.get("top_p"),
                    max_tokens=custom.get("maxTokens") or custom.get("max_tokens"),
                    system_prompt_prefix=custom.get("systemPromptPrefix"),
                    thinking_budget=custom.get("thinkingBudget") or custom.get("thinking_budget"),
                )

    return ModelProfile()


def list_profile_ids() -> list[str]:
    """List all available profile IDs."""
    return list(_DEFAULT_PROFILES.keys())
