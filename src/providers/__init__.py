"""Providers package — ported from bk/src/providers/.

LLM provider integrations: GitHub Copilot (auth, token, models),
Kilocode, and Qwen Portal OAuth.

Modules:
    github_copilot — GitHub Copilot device-flow auth, token exchange, and models
    kilocode       — Kilocode shared constants and model catalog
    qwen_portal    — Qwen Portal OAuth refresh
"""
from .github_copilot import (
    get_default_copilot_model_ids,
    build_copilot_model_definition,
    DEFAULT_COPILOT_API_BASE_URL,
)
from .kilocode import (
    KILOCODE_BASE_URL,
    KILOCODE_DEFAULT_MODEL_ID,
    KILOCODE_MODEL_CATALOG,
)
