"""Model display — ported from bk/src/agents/model-display.ts.

Formatting model names and IDs for display in CLI and UI.
"""
from __future__ import annotations

import re
from typing import Any


def format_model_display_name(
    model_id: str,
    provider: str | None = None,
    model_name: str | None = None,
) -> str:
    """Format a model ID into a human-readable display name."""
    if model_name:
        return model_name

    if not model_id:
        return "Unknown Model"

    # Strip provider prefix if present (e.g., "openai/gpt-4" -> "gpt-4")
    display = model_id
    if "/" in display:
        display = display.split("/", 1)[1]

    # Clean up common patterns
    display = _humanize_model_id(display)
    return display


def format_model_ref(model_id: str, provider: str | None = None) -> str:
    """Format a model reference as provider/model-id."""
    if not provider:
        return model_id
    return f"{provider}/{model_id}"


def truncate_model_display(name: str, max_length: int = 40) -> str:
    """Truncate a model display name to fit a max length."""
    if len(name) <= max_length:
        return name
    return name[: max_length - 3] + "..."


def _humanize_model_id(model_id: str) -> str:
    """Convert a model ID to a more human-readable format."""
    result = model_id.replace("-", " ").replace("_", " ")

    # Capitalize known tokens
    tokens = result.split()
    capitalized = []
    for token in tokens:
        if token.lower() in ("gpt", "claude", "gemini", "llama", "o1", "o3", "o4"):
            capitalized.append(token.upper() if len(token) <= 3 else token.capitalize())
        elif re.match(r"^\d", token):
            capitalized.append(token)
        else:
            capitalized.append(token.capitalize())

    return " ".join(capitalized)


def format_provider_display_name(provider_id: str) -> str:
    """Format a provider ID into a display name."""
    _PROVIDER_DISPLAY_NAMES = {
        "openai": "OpenAI",
        "anthropic": "Anthropic",
        "google": "Google",
        "deepseek": "DeepSeek",
        "openrouter": "OpenRouter",
        "together": "Together",
        "mistral": "Mistral",
        "groq": "Groq",
        "azure": "Azure OpenAI",
        "amazon-bedrock": "Amazon Bedrock",
        "vertex-ai": "Vertex AI",
        "ollama": "Ollama",
        "lmstudio": "LM Studio",
        "github-copilot": "GitHub Copilot",
        "byteplus": "BytePlus",
        "volcengine": "Volcengine",
        "chutes": "Chutes",
        "venice": "Venice",
    }
    return _PROVIDER_DISPLAY_NAMES.get(provider_id, provider_id.replace("-", " ").title())
