"""Browser routes utils — ported from bk/src/browser/routes/utils.ts + output-paths.ts + path-output.ts."""
from __future__ import annotations

from typing import Any


def json_response(data: Any, status: int = 200) -> dict[str, Any]:
    return {"status": status, "body": data}


def error_response(message: str, status: int = 400) -> dict[str, Any]:
    return {"status": status, "body": {"error": message}}


def resolve_output_path(base: str, filename: str) -> str:
    return f"{base.rstrip('/')}/{filename}"
