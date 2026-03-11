"""Model tool support — ported from bk/src/agents/model-tool-support.ts."""
from __future__ import annotations
from typing import Any

MODELS_WITHOUT_TOOL_SUPPORT = frozenset({
    "o1-preview", "o1-mini",
})

MODELS_WITH_PARALLEL_TOOL_USE = frozenset({
    "claude-opus-4-6", "claude-sonnet-4-20250514",
    "gpt-4o", "gpt-4o-mini", "gpt-4-turbo",
})

def supports_tool_use(model_id: str) -> bool:
    lower = model_id.strip().lower()
    return lower not in MODELS_WITHOUT_TOOL_SUPPORT

def supports_parallel_tool_use(model_id: str) -> bool:
    lower = model_id.strip().lower()
    return lower in MODELS_WITH_PARALLEL_TOOL_USE

def resolve_tool_choice_support(model_id: str) -> dict[str, bool]:
    return {
        "toolUse": supports_tool_use(model_id),
        "parallelToolUse": supports_parallel_tool_use(model_id),
    }
