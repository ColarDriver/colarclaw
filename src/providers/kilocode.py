"""Kilocode provider — ported from bk/src/providers/kilocode-shared.ts.

Kilocode shared constants and static model catalog.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

KILOCODE_BASE_URL = "https://api.kilo.ai/api/gateway/"
KILOCODE_DEFAULT_MODEL_ID = "kilo/auto"
KILOCODE_DEFAULT_MODEL_REF = f"kilocode/{KILOCODE_DEFAULT_MODEL_ID}"
KILOCODE_DEFAULT_MODEL_NAME = "Kilo Auto"
KILOCODE_DEFAULT_CONTEXT_WINDOW = 1_000_000
KILOCODE_DEFAULT_MAX_TOKENS = 128_000

KILOCODE_DEFAULT_COST = {
    "input": 0,
    "output": 0,
    "cacheRead": 0,
    "cacheWrite": 0,
}


@dataclass
class KilocodeModelCatalogEntry:
    id: str = ""
    name: str = ""
    reasoning: bool = False
    input: list[str] = field(default_factory=lambda: ["text", "image"])
    context_window: int | None = None
    max_tokens: int | None = None


KILOCODE_MODEL_CATALOG: list[KilocodeModelCatalogEntry] = [
    KilocodeModelCatalogEntry(
        id=KILOCODE_DEFAULT_MODEL_ID,
        name=KILOCODE_DEFAULT_MODEL_NAME,
        reasoning=True,
        input=["text", "image"],
        context_window=KILOCODE_DEFAULT_CONTEXT_WINDOW,
        max_tokens=KILOCODE_DEFAULT_MAX_TOKENS,
    ),
]
