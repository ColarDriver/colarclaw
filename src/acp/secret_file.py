"""ACP secret file — ported from bk/src/acp/secret-file.ts."""
from __future__ import annotations

import os
from pathlib import Path

MAX_SECRET_FILE_BYTES = 16 * 1024


def read_secret_from_file(file_path: str, label: str) -> str:
    resolved = file_path.strip()
    if not resolved:
        raise ValueError(f"{label} file path is empty.")
    if resolved.startswith("~"):
        resolved = os.path.expanduser(resolved)
    path = Path(resolved)

    if not path.exists():
        raise FileNotFoundError(f"Failed to inspect {label} file at {resolved}: file not found")
    if path.is_symlink():
        raise ValueError(f"{label} file at {resolved} must not be a symlink.")
    if not path.is_file():
        raise ValueError(f"{label} file at {resolved} must be a regular file.")
    stat = path.stat()
    if stat.st_size > MAX_SECRET_FILE_BYTES:
        raise ValueError(f"{label} file at {resolved} exceeds {MAX_SECRET_FILE_BYTES} bytes.")

    try:
        raw = path.read_text(encoding="utf-8")
    except Exception as err:
        raise IOError(f"Failed to read {label} file at {resolved}: {err}") from err

    secret = raw.strip()
    if not secret:
        raise ValueError(f"{label} file at {resolved} is empty.")
    return secret
