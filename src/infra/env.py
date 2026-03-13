"""Infra env — ported from bk/src/infra/env.ts, dotenv.ts.

Environment variable handling, logging, normalization, .env loading.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("infra.env")

_logged_env: set[str] = set()


def _format_env_value(value: str, redact: bool = False) -> str:
    if redact:
        return "<redacted>"
    single_line = " ".join(value.split()).strip()
    if len(single_line) <= 160:
        return single_line
    return f"{single_line[:160]}…"


def log_accepted_env_option(key: str, description: str, value: str | None = None, redact: bool = False) -> None:
    if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("NODE_ENV") == "test":
        return
    if key in _logged_env:
        return
    raw_value = value or os.environ.get(key, "")
    if not raw_value or not raw_value.strip():
        return
    _logged_env.add(key)
    logger.info(f"env: {key}={_format_env_value(raw_value, redact)} ({description})")


def normalize_zai_env() -> None:
    if not (os.environ.get("ZAI_API_KEY", "").strip()) and os.environ.get("Z_AI_API_KEY", "").strip():
        os.environ["ZAI_API_KEY"] = os.environ["Z_AI_API_KEY"]


def is_truthy_env_value(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in ("true", "1", "yes", "on")


def normalize_env() -> None:
    normalize_zai_env()


# ─── dotenv ───

def load_dotenv(path: str | Path | None = None, override: bool = False) -> dict[str, str]:
    """Load .env file, returns dict of loaded vars."""
    if path is None:
        path = Path.cwd() / ".env"
    else:
        path = Path(path)
    if not path.is_file():
        return {}
    loaded: dict[str, str] = {}
    try:
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key:
                    if override or key not in os.environ:
                        os.environ[key] = value
                    loaded[key] = value
    except OSError:
        pass
    return loaded


def resolve_dotenv_paths(workspace_dir: str | None = None) -> list[str]:
    candidates: list[str] = []
    if workspace_dir:
        candidates.append(os.path.join(workspace_dir, ".env"))
    candidates.append(os.path.join(str(Path.home()), ".env"))
    return [p for p in candidates if os.path.isfile(p)]
