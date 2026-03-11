"""Together models — ported from bk/src/agents/together-models.ts.

Together AI model catalog definitions.
"""
from __future__ import annotations

from dataclasses import dataclass

from .volc_models_shared import ModelDefinitionConfig, ModelDefinitionCost

TOGETHER_BASE_URL = "https://api.together.xyz/v1"
TOGETHER_DEFAULT_MODEL_ID = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
TOGETHER_DEFAULT_MODEL_REF = f"together/{TOGETHER_DEFAULT_MODEL_ID}"

TOGETHER_DEFAULT_COST = ModelDefinitionCost(
    input=0.00088,
    output=0.00088,
    cache_read=0,
    cache_write=0,
)


@dataclass
class TogetherModelEntry:
    id: str
    name: str
    reasoning: bool = False
    input: list[str] | None = None
    context_window: int = 128_000
    max_tokens: int = 4096


TOGETHER_MODEL_CATALOG: list[TogetherModelEntry] = [
    TogetherModelEntry(
        id="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        name="Llama 3.3 70B Instruct Turbo",
        input=["text"],
        context_window=128_000,
        max_tokens=4096,
    ),
    TogetherModelEntry(
        id="meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo",
        name="Llama 3.1 405B Instruct Turbo",
        input=["text"],
        context_window=128_000,
        max_tokens=4096,
    ),
    TogetherModelEntry(
        id="deepseek-ai/DeepSeek-R1",
        name="DeepSeek R1",
        reasoning=True,
        input=["text"],
        context_window=128_000,
        max_tokens=8192,
    ),
    TogetherModelEntry(
        id="Qwen/Qwen2.5-72B-Instruct-Turbo",
        name="Qwen 2.5 72B Instruct Turbo",
        input=["text"],
        context_window=128_000,
        max_tokens=4096,
    ),
]


def build_together_model_definition(entry: TogetherModelEntry) -> ModelDefinitionConfig:
    return ModelDefinitionConfig(
        id=entry.id,
        name=entry.name,
        reasoning=entry.reasoning,
        input=entry.input or ["text"],
        cost=TOGETHER_DEFAULT_COST,
        context_window=entry.context_window,
        max_tokens=entry.max_tokens,
    )
