"""Auto-reply model — ported from bk/src/auto-reply/model.ts.

Model directive extraction from message body (/model provider/model).
"""
from __future__ import annotations

import re
from typing import Any


def extract_model_directive(
    body: str | None = None,
    aliases: list[str] | None = None,
) -> dict[str, Any]:
    if not body:
        return {"cleaned": "", "has_directive": False}

    model_match = re.search(
        r"(?:^|\s)/model(?=$|\s|:)\s*:?\s*([A-Za-z0-9_.:\@-]+(?:/[A-Za-z0-9_.:\@-]+)*)?",
        body, re.IGNORECASE,
    )

    alias_match = None
    clean_aliases = [a.strip() for a in (aliases or []) if a.strip()]
    if not model_match and clean_aliases:
        escaped = "|".join(re.escape(a) for a in clean_aliases)
        alias_match = re.search(
            rf"(?:^|\s)/({escaped})(?=$|\s|:)(?:\s*:\s*)?",
            body, re.IGNORECASE,
        )

    match = model_match or alias_match
    raw = (model_match.group(1) or "").strip() if model_match else (
        (alias_match.group(1) or "").strip() if alias_match else None
    )

    raw_model = raw
    raw_profile: str | None = None
    if raw and "@" in raw:
        parts = raw.rsplit("@", 1)
        raw_model = parts[0]
        raw_profile = parts[1] if len(parts) > 1 else None

    if match:
        cleaned = re.sub(re.escape(match.group(0)), " ", body, count=1)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
    else:
        cleaned = body.strip()

    return {
        "cleaned": cleaned,
        "raw_model": raw_model,
        "raw_profile": raw_profile,
        "has_directive": bool(match),
    }
