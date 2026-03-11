"""Model forward compat — ported from bk/src/agents/model-forward-compat.ts."""
from __future__ import annotations
import re
from typing import Any

def normalize_model_id(model_id: str) -> str:
    return model_id.strip().lower()

def is_known_model_pattern(model_id: str) -> bool:
    patterns = [
        r"^claude-",
        r"^gpt-",
        r"^gemini-",
        r"^mistral-",
        r"^llama-",
        r"^deepseek-",
        r"^qwen",
        r"^command-",
    ]
    lower = model_id.lower()
    return any(re.match(p, lower) for p in patterns)

def infer_provider_from_model_id(model_id: str) -> str | None:
    lower = model_id.lower()
    if lower.startswith("claude-"):
        return "anthropic"
    if lower.startswith("gpt-") or lower.startswith("o1-") or lower.startswith("o3-"):
        return "openai"
    if lower.startswith("gemini-"):
        return "google"
    if lower.startswith("mistral-"):
        return "mistral"
    if lower.startswith("deepseek-"):
        return "deepseek"
    if lower.startswith("command-"):
        return "cohere"
    if lower.startswith("llama-"):
        return "groq"
    return None
