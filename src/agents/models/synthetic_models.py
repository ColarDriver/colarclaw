"""Synthetic models — ported from bk/src/agents/synthetic-models.ts.

Definitions for synthetic/virtual model identifiers used internally.
"""
from __future__ import annotations

from dataclasses import dataclass

# Synthetic model IDs used for internal routing
SYNTHETIC_MODEL_ECHO = "synthetic/echo"
SYNTHETIC_MODEL_NOOP = "synthetic/noop"
SYNTHETIC_MODEL_PASSTHROUGH = "synthetic/passthrough"
SYNTHETIC_MODEL_DUMMY = "synthetic/dummy"

_SYNTHETIC_MODEL_IDS = frozenset({
    SYNTHETIC_MODEL_ECHO,
    SYNTHETIC_MODEL_NOOP,
    SYNTHETIC_MODEL_PASSTHROUGH,
    SYNTHETIC_MODEL_DUMMY,
})


def is_synthetic_model(model_id: str) -> bool:
    """Check if a model ID refers to a synthetic/virtual model."""
    return model_id in _SYNTHETIC_MODEL_IDS or model_id.startswith("synthetic/")


def list_synthetic_models() -> list[str]:
    """List all known synthetic model IDs."""
    return sorted(_SYNTHETIC_MODEL_IDS)
