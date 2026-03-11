"""Model config helpers — ported from bk/src/agents/tools/model-config.helpers.ts."""
from __future__ import annotations

from typing import Any


def resolve_model_config(
    model_id: str,
    provider: str | None = None,
    config: Any = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"model_id": model_id}
    if provider:
        result["provider"] = provider
    if config:
        overrides = getattr(config, "model_overrides", None)
        if isinstance(overrides, dict) and model_id in overrides:
            result.update(overrides[model_id])
    return result
