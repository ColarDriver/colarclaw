"""Venice models — ported from bk/src/agents/venice-models.ts.

Venice AI model catalog definitions.
"""
from __future__ import annotations

from .volc_models_shared import ModelDefinitionConfig, ModelDefinitionCost

VENICE_BASE_URL = "https://api.venice.ai/api/v1"
VENICE_DEFAULT_MODEL_ID = "llama-3.3-70b"
VENICE_DEFAULT_MODEL_REF = f"venice/{VENICE_DEFAULT_MODEL_ID}"

VENICE_DEFAULT_COST = ModelDefinitionCost(
    input=0,
    output=0,
    cache_read=0,
    cache_write=0,
)

VENICE_MODEL_CATALOG: list[dict[str, object]] = [
    {
        "id": "llama-3.3-70b",
        "name": "Llama 3.3 70B",
        "reasoning": False,
        "input": ["text"],
        "context_window": 128_000,
        "max_tokens": 4096,
    },
    {
        "id": "llama-3.1-405b",
        "name": "Llama 3.1 405B",
        "reasoning": False,
        "input": ["text"],
        "context_window": 128_000,
        "max_tokens": 4096,
    },
    {
        "id": "deepseek-r1-671b",
        "name": "DeepSeek R1 671B",
        "reasoning": True,
        "input": ["text"],
        "context_window": 128_000,
        "max_tokens": 8192,
    },
    {
        "id": "qwen-2.5-coder-32b",
        "name": "Qwen 2.5 Coder 32B",
        "reasoning": False,
        "input": ["text"],
        "context_window": 128_000,
        "max_tokens": 4096,
    },
]


def build_venice_model_definition(entry: dict[str, object]) -> ModelDefinitionConfig:
    return ModelDefinitionConfig(
        id=str(entry.get("id", "")),
        name=str(entry.get("name", "")),
        reasoning=bool(entry.get("reasoning", False)),
        input=list(entry.get("input", ["text"])),  # type: ignore
        cost=VENICE_DEFAULT_COST,
        context_window=int(entry.get("context_window", 128_000)),  # type: ignore
        max_tokens=int(entry.get("max_tokens", 4096)),  # type: ignore
    )
