"""Anthropic payload log — ported from bk/src/agents/anthropic-payload-log.ts."""
from __future__ import annotations
import json
import logging
import os
import time
from typing import Any
from agents.payload_redaction import redact_image_data_for_diagnostics

log = logging.getLogger("openclaw.agents.anthropic_payload_log")

def log_anthropic_payload(
    payload: dict[str, Any],
    direction: str = "request",
    log_dir: str | None = None,
) -> None:
    if not os.environ.get("OPENCLAW_ANTHROPIC_PAYLOAD_LOG"):
        return
    target_dir = log_dir or os.path.join(os.path.expanduser("~/.openclaw"), "logs", "anthropic")
    os.makedirs(target_dir, exist_ok=True)
    redacted = redact_image_data_for_diagnostics(payload)
    filename = f"{direction}_{int(time.time() * 1000)}.json"
    filepath = os.path.join(target_dir, filename)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(redacted, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log.debug("Failed to log anthropic payload: %s", e)
