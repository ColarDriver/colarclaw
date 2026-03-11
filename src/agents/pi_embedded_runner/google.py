"""Pi embedded runner Google — ported from bk/src/agents/pi-embedded-runner/google.ts.

Google-specific API extensions for Gemini models.
"""
from __future__ import annotations

from typing import Any


def build_google_safety_settings() -> list[dict[str, str]]:
    """Build default safety settings for Google/Gemini models."""
    categories = [
        "HARM_CATEGORY_HARASSMENT",
        "HARM_CATEGORY_HATE_SPEECH",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "HARM_CATEGORY_DANGEROUS_CONTENT",
    ]
    return [{"category": c, "threshold": "BLOCK_NONE"} for c in categories]


def is_google_provider(provider: str) -> bool:
    normalized = provider.lower().strip()
    return normalized in ("google", "gemini", "google-ai", "google-vertex")


def build_google_extra_params(model_id: str) -> dict[str, Any]:
    return {
        "safetySettings": build_google_safety_settings(),
    }
