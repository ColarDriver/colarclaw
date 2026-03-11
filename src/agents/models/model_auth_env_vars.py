"""Model auth env vars — ported from bk/src/agents/model-auth-env-vars.ts."""
from __future__ import annotations
import os

MODEL_AUTH_ENV_VARS = [
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "MISTRAL_API_KEY",
    "GROQ_API_KEY",
    "TOGETHER_API_KEY",
    "XAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "COHERE_API_KEY",
    "CO_API_KEY",
    "FIREWORKS_API_KEY",
    "OPENROUTER_API_KEY",
    "PERPLEXITY_API_KEY",
    "PPLX_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "GOOGLE_APPLICATION_CREDENTIALS",
]

def collect_model_auth_env_snapshot() -> dict[str, bool]:
    return {var: bool(os.environ.get(var, "").strip()) for var in MODEL_AUTH_ENV_VARS}

def has_any_model_auth_env() -> bool:
    return any(os.environ.get(var, "").strip() for var in MODEL_AUTH_ENV_VARS)
