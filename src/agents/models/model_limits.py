"""Model limits — ported from bk/src/agents/model-limits.ts.

Model context window and token limits.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ModelLimits:
    context_window: int = 128_000
    max_output_tokens: int = 4096
    max_images: int = 20
    supports_vision: bool = False
    supports_function_calling: bool = True
    supports_streaming: bool = True
    supports_json_mode: bool = False
    supports_reasoning: bool = False


# Known model limits (lower-cased keys)
_KNOWN_MODEL_LIMITS: dict[str, ModelLimits] = {
    "gpt-4o": ModelLimits(context_window=128_000, max_output_tokens=16_384, supports_vision=True, supports_json_mode=True),
    "gpt-4o-mini": ModelLimits(context_window=128_000, max_output_tokens=16_384, supports_vision=True, supports_json_mode=True),
    "gpt-4-turbo": ModelLimits(context_window=128_000, max_output_tokens=4096, supports_vision=True, supports_json_mode=True),
    "gpt-4": ModelLimits(context_window=8192, max_output_tokens=4096),
    "o1": ModelLimits(context_window=200_000, max_output_tokens=100_000, supports_reasoning=True),
    "o1-mini": ModelLimits(context_window=128_000, max_output_tokens=65_536, supports_reasoning=True),
    "o3": ModelLimits(context_window=200_000, max_output_tokens=100_000, supports_reasoning=True),
    "o3-mini": ModelLimits(context_window=200_000, max_output_tokens=100_000, supports_reasoning=True),
    "o4-mini": ModelLimits(context_window=200_000, max_output_tokens=100_000, supports_reasoning=True),
    "claude-sonnet-4-5-20250514": ModelLimits(context_window=200_000, max_output_tokens=8192, supports_vision=True),
    "claude-opus-4-0-20250514": ModelLimits(context_window=200_000, max_output_tokens=8192, supports_vision=True),
    "claude-3-5-haiku-20241022": ModelLimits(context_window=200_000, max_output_tokens=8192, supports_vision=True),
    "gemini-2.5-pro": ModelLimits(context_window=1_000_000, max_output_tokens=65_536, supports_vision=True, supports_reasoning=True),
    "gemini-2.5-flash": ModelLimits(context_window=1_000_000, max_output_tokens=65_536, supports_vision=True),
    "deepseek-chat": ModelLimits(context_window=128_000, max_output_tokens=8192),
    "deepseek-reasoner": ModelLimits(context_window=128_000, max_output_tokens=8192, supports_reasoning=True),
}


def resolve_model_limits(
    model_id: str,
    context_window: int | None = None,
    max_output_tokens: int | None = None,
) -> ModelLimits:
    """Resolve limits for a model, falling back to known defaults."""
    normalized = (model_id or "").lower().strip()

    known = _KNOWN_MODEL_LIMITS.get(normalized)
    if known:
        return ModelLimits(
            context_window=context_window or known.context_window,
            max_output_tokens=max_output_tokens or known.max_output_tokens,
            max_images=known.max_images,
            supports_vision=known.supports_vision,
            supports_function_calling=known.supports_function_calling,
            supports_streaming=known.supports_streaming,
            supports_json_mode=known.supports_json_mode,
            supports_reasoning=known.supports_reasoning,
        )

    return ModelLimits(
        context_window=context_window or 128_000,
        max_output_tokens=max_output_tokens or 4096,
    )


def get_context_window(model_id: str) -> int:
    """Get the context window for a model."""
    return resolve_model_limits(model_id).context_window


def get_max_output_tokens(model_id: str) -> int:
    """Get the max output tokens for a model."""
    return resolve_model_limits(model_id).max_output_tokens
