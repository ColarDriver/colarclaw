"""Model budget — ported from bk/src/agents/model-budget.ts.

Token budget management for model contexts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_CONTEXT_WINDOW = 128_000
DEFAULT_MAX_OUTPUT_TOKENS = 4096
DEFAULT_BUDGET_RESERVE_RATIO = 0.1
MIN_BUDGET_RESERVE = 1000


@dataclass
class ModelBudget:
    context_window: int = DEFAULT_CONTEXT_WINDOW
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    reserved_tokens: int = 0
    available_input_tokens: int = 0


def compute_model_budget(
    context_window: int | None = None,
    max_output_tokens: int | None = None,
    reserve_ratio: float = DEFAULT_BUDGET_RESERVE_RATIO,
) -> ModelBudget:
    """Compute the available token budget for a model."""
    ctx = context_window or DEFAULT_CONTEXT_WINDOW
    max_out = max_output_tokens or DEFAULT_MAX_OUTPUT_TOKENS

    reserved = max(int(ctx * reserve_ratio), MIN_BUDGET_RESERVE)
    available = max(0, ctx - max_out - reserved)

    return ModelBudget(
        context_window=ctx,
        max_output_tokens=max_out,
        reserved_tokens=reserved,
        available_input_tokens=available,
    )


def estimate_token_usage(
    messages: list[dict[str, Any]],
    chars_per_token: float = 4.0,
) -> int:
    """Rough estimate of token usage from message content."""
    total_chars = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text", "")
                    if isinstance(text, str):
                        total_chars += len(text)
    return int(total_chars / chars_per_token)


def is_within_budget(
    estimated_tokens: int,
    budget: ModelBudget,
) -> bool:
    """Check if estimated tokens fit within the available budget."""
    return estimated_tokens <= budget.available_input_tokens
