"""OpenCode Zen models — ported from bk/src/agents/opencode-zen-models.ts.

OpenCode Zen model catalog definitions.
"""
from __future__ import annotations

from .volc_models_shared import ModelDefinitionConfig, ModelDefinitionCost

OPENCODE_ZEN_BASE_URL = "https://api.opencode.ai/v1"
OPENCODE_ZEN_DEFAULT_MODEL_ID = "zen-1"
OPENCODE_ZEN_DEFAULT_MODEL_REF = f"opencode-zen/{OPENCODE_ZEN_DEFAULT_MODEL_ID}"

OPENCODE_ZEN_DEFAULT_COST = ModelDefinitionCost(
    input=0,
    output=0,
    cache_read=0,
    cache_write=0,
)

OPENCODE_ZEN_MODEL_CATALOG: list[dict[str, object]] = [
    {
        "id": "zen-1",
        "name": "Zen 1",
        "reasoning": False,
        "input": ["text"],
        "context_window": 128_000,
        "max_tokens": 4096,
    },
]


def build_opencode_zen_model_definition(entry: dict[str, object]) -> ModelDefinitionConfig:
    return ModelDefinitionConfig(
        id=str(entry.get("id", "")),
        name=str(entry.get("name", "")),
        reasoning=bool(entry.get("reasoning", False)),
        input=list(entry.get("input", ["text"])),  # type: ignore
        cost=OPENCODE_ZEN_DEFAULT_COST,
        context_window=int(entry.get("context_window", 128_000)),  # type: ignore
        max_tokens=int(entry.get("max_tokens", 4096)),  # type: ignore
    )
