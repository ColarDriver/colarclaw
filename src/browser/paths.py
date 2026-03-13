"""Browser paths — ported from bk/src/browser/paths.ts + proxy-files.ts + output-atomic.ts + safe-filename.ts + target-id.ts + trash.ts + form-fields.ts + resolved-config-refresh.ts + session-tab-registry.ts + control-service.ts.

File paths, output, target ID, trash, form fields, config refresh, tab registry.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any


def get_browser_data_dir() -> str:
    home = Path.home()
    return str(home / ".config" / "openclaw" / "browser")


def get_browser_output_dir() -> str:
    return str(Path(get_browser_data_dir()) / "output")


def safe_filename(raw: str, max_length: int = 200) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw.strip())
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
    return cleaned or "unnamed"


def resolve_target_id(raw: str | None) -> str | None:
    if not raw:
        return None
    trimmed = raw.strip()
    return trimmed if trimmed else None


def write_output_atomic(path: str, content: bytes | str) -> None:
    """Write file atomically via temp file + rename."""
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    mode = "wb" if isinstance(content, bytes) else "w"
    fd, tmp = tempfile.mkstemp(dir=parent)
    try:
        with os.fdopen(fd, mode) as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def move_to_trash(path: str) -> str | None:
    """Move file to trash directory (placeholder)."""
    return None


# Proxy files
def write_proxy_pac_file(proxy_url: str, output: str) -> None:
    pass


# Form fields
FORM_INPUT_TYPES = frozenset(["text", "password", "email", "search", "tel", "url", "number"])


def is_form_input_type(input_type: str) -> bool:
    return input_type.lower() in FORM_INPUT_TYPES


# Config refresh
async def refresh_resolved_config() -> None:
    pass


# Session tab registry
_tab_registry: dict[str, str] = {}


def register_tab(session_key: str, target_id: str) -> None:
    _tab_registry[session_key] = target_id


def get_registered_tab(session_key: str) -> str | None:
    return _tab_registry.get(session_key)


def unregister_tab(session_key: str) -> None:
    _tab_registry.pop(session_key, None)


# Control service
async def get_control_service_url(cfg: Any = None) -> str:
    return "http://127.0.0.1:9800"
