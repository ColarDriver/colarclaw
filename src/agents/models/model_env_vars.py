"""Model env vars — ported from bk/src/agents/model-env-vars.ts.

Resolution of environment variables for model/provider authentication.
"""
from __future__ import annotations

import os
from typing import Any

from .model_selection import normalize_provider_id

# Standard env var names per provider
_PROVIDER_ENV_VARS: dict[str, list[str]] = {
    "openai": ["OPENAI_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    "google": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "openrouter": ["OPENROUTER_API_KEY"],
    "together": ["TOGETHER_API_KEY"],
    "mistral": ["MISTRAL_API_KEY"],
    "groq": ["GROQ_API_KEY"],
    "azure": ["AZURE_OPENAI_API_KEY", "AZURE_API_KEY"],
    "amazon-bedrock": ["AWS_ACCESS_KEY_ID"],
    "ollama": [],
    "lmstudio": [],
    "github-copilot": ["GITHUB_TOKEN"],
    "byteplus": ["BYTEPLUS_API_KEY"],
    "volcengine": ["VOLC_API_KEY", "ARK_API_KEY"],
    "chutes": ["CHUTES_API_KEY"],
    "venice": ["VENICE_API_KEY"],
}

# Base URL env vars per provider
_PROVIDER_BASE_URL_VARS: dict[str, str] = {
    "openai": "OPENAI_BASE_URL",
    "ollama": "OLLAMA_BASE_URL",
    "lmstudio": "LMSTUDIO_BASE_URL",
    "azure": "AZURE_OPENAI_ENDPOINT",
}


def resolve_model_api_key(
    provider: str | None = None,
    env_var_name: str | None = None,
) -> str | None:
    """Resolve the API key for a provider from environment variables."""
    if env_var_name:
        return os.environ.get(env_var_name)

    norm = normalize_provider_id(provider or "")
    env_vars = _PROVIDER_ENV_VARS.get(norm, [])

    for var in env_vars:
        value = os.environ.get(var, "").strip()
        if value:
            return value
    return None


def resolve_model_base_url(
    provider: str | None = None,
    env_var_name: str | None = None,
) -> str | None:
    """Resolve the base URL for a provider from environment variables."""
    if env_var_name:
        return os.environ.get(env_var_name, "").strip() or None

    norm = normalize_provider_id(provider or "")
    var = _PROVIDER_BASE_URL_VARS.get(norm)
    if var:
        return os.environ.get(var, "").strip() or None
    return None


def list_provider_env_vars(provider: str) -> list[str]:
    """List the environment variable names used for a provider."""
    norm = normalize_provider_id(provider)
    return list(_PROVIDER_ENV_VARS.get(norm, []))


def has_provider_api_key(provider: str) -> bool:
    """Check if the required API key env var is set for a provider."""
    return resolve_model_api_key(provider=provider) is not None
