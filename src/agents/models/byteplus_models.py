"""BytePlus models — ported from bk/src/agents/byteplus-models.ts.

BytePlus ARK model catalog and definition builder.
"""
from __future__ import annotations

from .volc_models_shared import (
    ModelDefinitionConfig,
    ModelDefinitionCost,
    VOLC_MODEL_GLM_4_7,
    VOLC_MODEL_KIMI_K2_5,
    VOLC_SHARED_CODING_MODEL_CATALOG,
    VolcModelCatalogEntry,
    build_volc_model_definition,
)

BYTEPLUS_BASE_URL = "https://ark.ap-southeast.bytepluses.com/api/v3"
BYTEPLUS_CODING_BASE_URL = "https://ark.ap-southeast.bytepluses.com/api/coding/v3"
BYTEPLUS_DEFAULT_MODEL_ID = "seed-1-8-251228"
BYTEPLUS_CODING_DEFAULT_MODEL_ID = "ark-code-latest"
BYTEPLUS_DEFAULT_MODEL_REF = f"byteplus/{BYTEPLUS_DEFAULT_MODEL_ID}"

BYTEPLUS_DEFAULT_COST = ModelDefinitionCost(
    input=0.0001,
    output=0.0002,
    cache_read=0,
    cache_write=0,
)

BYTEPLUS_MODEL_CATALOG: list[VolcModelCatalogEntry] = [
    VolcModelCatalogEntry(
        id="seed-1-8-251228",
        name="Seed 1.8",
        reasoning=False,
        input=["text", "image"],
        context_window=256000,
        max_tokens=4096,
    ),
    VOLC_MODEL_KIMI_K2_5,
    VOLC_MODEL_GLM_4_7,
]

BYTEPLUS_CODING_MODEL_CATALOG = VOLC_SHARED_CODING_MODEL_CATALOG


def build_byteplus_model_definition(
    entry: VolcModelCatalogEntry,
) -> ModelDefinitionConfig:
    return build_volc_model_definition(entry, BYTEPLUS_DEFAULT_COST)
