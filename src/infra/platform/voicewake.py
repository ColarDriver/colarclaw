"""Infra voicewake — ported from bk/src/infra/voicewake.ts.

Voice wake trigger configuration management: load, save, and sanitize
voice wake trigger words.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("infra.voicewake")

DEFAULT_TRIGGERS = ["openclaw", "claude", "computer"]


@dataclass
class VoiceWakeConfig:
    triggers: list[str] = field(default_factory=lambda: list(DEFAULT_TRIGGERS))
    updated_at_ms: float = 0.0


def _resolve_voicewake_path(base_dir: str | None = None) -> str:
    root = base_dir or os.path.join(str(Path.home()), ".openclaw")
    return os.path.join(root, "settings", "voicewake.json")


def _sanitize_triggers(triggers: list[str] | None) -> list[str]:
    if not triggers:
        return list(DEFAULT_TRIGGERS)
    cleaned = [w.strip() for w in triggers if isinstance(w, str) and w.strip()]
    return cleaned if cleaned else list(DEFAULT_TRIGGERS)


def default_voice_wake_triggers() -> list[str]:
    return list(DEFAULT_TRIGGERS)


async def load_voice_wake_config(base_dir: str | None = None) -> VoiceWakeConfig:
    """Load voice wake configuration from disk."""
    file_path = _resolve_voicewake_path(base_dir)
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return VoiceWakeConfig()

    triggers = _sanitize_triggers(data.get("triggers"))
    updated_at_ms = data.get("updatedAtMs", 0)
    if not isinstance(updated_at_ms, (int, float)) or updated_at_ms <= 0:
        updated_at_ms = 0.0

    return VoiceWakeConfig(triggers=triggers, updated_at_ms=float(updated_at_ms))


async def set_voice_wake_triggers(
    triggers: list[str],
    base_dir: str | None = None,
) -> VoiceWakeConfig:
    """Save updated voice wake triggers to disk."""
    sanitized = _sanitize_triggers(triggers)
    file_path = _resolve_voicewake_path(base_dir)

    config = VoiceWakeConfig(
        triggers=sanitized,
        updated_at_ms=time.time() * 1000,
    )

    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    tmp = file_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"triggers": config.triggers, "updatedAtMs": config.updated_at_ms}, f, indent=2)
        f.write("\n")
    os.replace(tmp, file_path)

    return config
