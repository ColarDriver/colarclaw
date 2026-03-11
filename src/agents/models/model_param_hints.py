"""Model param hints — ported from bk/src/agents/model-param-hints.ts.

Model parameter hint resolution for provider-specific tuning.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .model_selection import normalize_provider_id


@dataclass
class ModelParamHints:
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    stop_sequences: list[str] | None = None
    seed: int | None = None


def resolve_model_param_hints(
    provider: str | None = None,
    model_id: str | None = None,
    model_api: str | None = None,
    config: dict[str, Any] | None = None,
) -> ModelParamHints:
    """Resolve provider-specific parameter hints."""
    norm_provider = normalize_provider_id(provider or "")
    hints = ModelParamHints()

    if config:
        if "temperature" in config:
            hints.temperature = float(config["temperature"])
        if "top_p" in config or "topP" in config:
            hints.top_p = float(config.get("top_p") or config.get("topP"))
        if "top_k" in config or "topK" in config:
            hints.top_k = int(config.get("top_k") or config.get("topK"))
        if "frequency_penalty" in config or "frequencyPenalty" in config:
            hints.frequency_penalty = float(config.get("frequency_penalty") or config.get("frequencyPenalty"))
        if "presence_penalty" in config or "presencePenalty" in config:
            hints.presence_penalty = float(config.get("presence_penalty") or config.get("presencePenalty"))
        if "stop" in config or "stopSequences" in config:
            stops = config.get("stop") or config.get("stopSequences")
            if isinstance(stops, list):
                hints.stop_sequences = stops
        if "seed" in config:
            hints.seed = int(config["seed"])

    return hints
