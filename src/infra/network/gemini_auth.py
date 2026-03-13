"""Infra gemini_auth — ported from bk/src/infra/gemini-auth.ts.

Shared Gemini authentication utilities, supporting both API key and OAuth JSON.
"""
from __future__ import annotations

import json


def parse_gemini_auth(api_key: str) -> dict[str, dict[str, str]]:
    """Parse Gemini API key and return appropriate auth headers.

    Supports both:
    - Traditional API key strings
    - OAuth JSON format: {"token": "...", "projectId": "..."}
    """
    if api_key.startswith("{"):
        try:
            parsed = json.loads(api_key)
            token = parsed.get("token")
            if isinstance(token, str) and token:
                return {
                    "headers": {
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    }
                }
        except (json.JSONDecodeError, TypeError):
            pass

    # Default: traditional API key
    return {
        "headers": {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        }
    }
