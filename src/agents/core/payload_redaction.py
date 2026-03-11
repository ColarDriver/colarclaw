"""Payload redaction — ported from bk/src/agents/payload-redaction.ts.

Redacts sensitive data (base64 images, API keys) from payloads for logging/diagnostics.
"""
from __future__ import annotations
import re
from typing import Any

IMAGE_DATA_PATTERN = re.compile(r"^data:image/[^;]+;base64,", re.IGNORECASE)
API_KEY_PATTERN = re.compile(r"(sk-|key-|api[_-]?key)[a-zA-Z0-9_-]{10,}", re.IGNORECASE)

def redact_image_data_for_diagnostics(data: Any) -> Any:
    if isinstance(data, str):
        if IMAGE_DATA_PATTERN.match(data):
            return "[REDACTED_IMAGE_DATA]"
        if len(data) > 500 and all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=" for c in data[:100]):
            return "[REDACTED_BASE64]"
        return data
    if isinstance(data, list):
        return [redact_image_data_for_diagnostics(item) for item in data]
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            if k in ("data", "image_data", "base64", "source_data") and isinstance(v, str) and len(v) > 200:
                result[k] = "[REDACTED]"
            elif k in ("api_key", "apiKey", "accessToken", "access_token", "token", "secret"):
                result[k] = "[REDACTED_KEY]"
            else:
                result[k] = redact_image_data_for_diagnostics(v)
        return result
    return data

def redact_api_keys(text: str) -> str:
    return API_KEY_PATTERN.sub("[REDACTED_KEY]", text)
