"""Image sanitization — ported from bk/src/agents/image-sanitization.ts."""
from __future__ import annotations
import base64
import re
from typing import Any

MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20MB

SUPPORTED_MIME_TYPES = frozenset({
    "image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml",
})

DATA_URL_RE = re.compile(r"^data:([^;,]+);base64,(.+)$", re.DOTALL)

def is_supported_image_mime(mime_type: str) -> bool:
    return mime_type.lower().strip() in SUPPORTED_MIME_TYPES

def validate_image_data_url(url: str) -> dict[str, Any]:
    m = DATA_URL_RE.match(url)
    if not m:
        return {"valid": False, "error": "Not a valid data URL"}
    mime = m.group(1).strip().lower()
    if not is_supported_image_mime(mime):
        return {"valid": False, "error": f"Unsupported mime type: {mime}"}
    try:
        data = base64.b64decode(m.group(2))
    except Exception:
        return {"valid": False, "error": "Invalid base64 data"}
    if len(data) > MAX_IMAGE_BYTES:
        return {"valid": False, "error": f"Image too large: {len(data)} bytes"}
    return {"valid": True, "mime": mime, "size": len(data)}

def sanitize_image_url(url: str) -> str | None:
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("data:"):
        result = validate_image_data_url(url)
        return url if result["valid"] else None
    return None
