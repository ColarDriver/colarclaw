"""Vercel AI gateway — ported from bk/src/agents/vercel-ai-gateway.ts.

Vercel AI gateway integration helpers.
"""
from __future__ import annotations

import os
from typing import Any

VERCEL_AI_GATEWAY_URL = "https://gateway.vercel.ai/v1"


def resolve_vercel_ai_gateway_url() -> str:
    """Resolve the Vercel AI gateway URL from env or default."""
    return os.environ.get("VERCEL_AI_GATEWAY_URL", "").strip() or VERCEL_AI_GATEWAY_URL


def resolve_vercel_ai_gateway_api_key() -> str | None:
    """Resolve the API key for Vercel AI gateway."""
    return os.environ.get("VERCEL_AI_GATEWAY_API_KEY", "").strip() or None


def is_vercel_ai_gateway_configured() -> bool:
    """Check if the Vercel AI gateway is configured."""
    return resolve_vercel_ai_gateway_api_key() is not None


def build_vercel_ai_gateway_headers(api_key: str | None = None) -> dict[str, str]:
    """Build HTTP headers for Vercel AI gateway requests."""
    key = api_key or resolve_vercel_ai_gateway_api_key()
    if not key:
        return {}
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
