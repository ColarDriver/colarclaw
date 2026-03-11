"""Volcengine model shared definitions — ported from bk/src/agents/volc-models.shared.ts.

Shared model catalog entries and builder for Volcengine-based providers
(BytePlus, Volcengine, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class VolcModelCatalogEntry:
    id: str
    name: str
    reasoning: bool
    input: list[str]
    context_window: int
    max_tokens: int


@dataclass
class ModelDefinitionCost:
    input: float = 0
    output: float = 0
    cache_read: float = 0
    cache_write: float = 0


@dataclass
class ModelDefinitionConfig:
    id: str
    name: str
    reasoning: bool
    input: list[str]
    cost: ModelDefinitionCost
    context_window: int
    max_tokens: int


VOLC_MODEL_KIMI_K2_5 = VolcModelCatalogEntry(
    id="kimi-k2-5-260127",
    name="Kimi K2.5",
    reasoning=False,
    input=["text", "image"],
    context_window=256000,
    max_tokens=4096,
)

VOLC_MODEL_GLM_4_7 = VolcModelCatalogEntry(
    id="glm-4-7-251222",
    name="GLM 4.7",
    reasoning=False,
    input=["text", "image"],
    context_window=200000,
    max_tokens=4096,
)

VOLC_SHARED_CODING_MODEL_CATALOG: list[VolcModelCatalogEntry] = [
    VolcModelCatalogEntry(
        id="ark-code-latest", name="Ark Coding Plan", reasoning=False,
        input=["text"], context_window=256000, max_tokens=4096,
    ),
    VolcModelCatalogEntry(
        id="doubao-seed-code", name="Doubao Seed Code", reasoning=False,
        input=["text"], context_window=256000, max_tokens=4096,
    ),
    VolcModelCatalogEntry(
        id="glm-4.7", name="GLM 4.7 Coding", reasoning=False,
        input=["text"], context_window=200000, max_tokens=4096,
    ),
    VolcModelCatalogEntry(
        id="kimi-k2-thinking", name="Kimi K2 Thinking", reasoning=False,
        input=["text"], context_window=256000, max_tokens=4096,
    ),
    VolcModelCatalogEntry(
        id="kimi-k2.5", name="Kimi K2.5 Coding", reasoning=False,
        input=["text"], context_window=256000, max_tokens=4096,
    ),
]


def build_volc_model_definition(
    entry: VolcModelCatalogEntry,
    cost: ModelDefinitionCost,
) -> ModelDefinitionConfig:
    return ModelDefinitionConfig(
        id=entry.id,
        name=entry.name,
        reasoning=entry.reasoning,
        input=list(entry.input),
        cost=cost,
        context_window=entry.context_window,
        max_tokens=entry.max_tokens,
    )
