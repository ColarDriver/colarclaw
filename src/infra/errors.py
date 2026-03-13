"""Infra errors — ported from bk/src/infra/errors.ts.

Error extraction, formatting, errno checking, error graph traversal.
"""
from __future__ import annotations

import json
import traceback
from typing import Any, Callable, Iterable


def extract_error_code(err: Any) -> str | None:
    if err is None or not isinstance(err, (Exception, dict)):
        return None
    if isinstance(err, dict):
        code = err.get("code")
    else:
        code = getattr(err, "code", None) or getattr(err, "errno", None)
    if isinstance(code, str):
        return code
    if isinstance(code, int):
        return str(code)
    return None


def read_error_name(err: Any) -> str:
    if err is None:
        return ""
    if isinstance(err, Exception):
        return type(err).__name__
    if isinstance(err, dict):
        name = err.get("name")
        return str(name) if isinstance(name, str) else ""
    return ""


def collect_error_graph_candidates(
    err: Any,
    resolve_nested: Callable[[dict[str, Any]], Iterable[Any]] | None = None,
) -> list[Any]:
    queue: list[Any] = [err]
    seen: set[int] = set()
    candidates: list[Any] = []
    while queue:
        current = queue.pop(0)
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        candidates.append(current)
        if resolve_nested and isinstance(current, dict):
            for nested in resolve_nested(current):
                if nested is not None and id(nested) not in seen:
                    queue.append(nested)
    return candidates


def is_errno(err: Any) -> bool:
    return isinstance(err, OSError)


def has_errno_code(err: Any, code: int) -> bool:
    return isinstance(err, OSError) and err.errno == code


def format_error_message(err: Any) -> str:
    if isinstance(err, Exception):
        return str(err) or type(err).__name__ or "Error"
    if isinstance(err, str):
        return err
    if isinstance(err, (int, float, bool)):
        return str(err)
    try:
        return json.dumps(err)
    except (TypeError, ValueError):
        return repr(err)


def format_uncaught_error(err: Any) -> str:
    code = extract_error_code(err)
    if code == "INVALID_CONFIG":
        return format_error_message(err)
    if isinstance(err, Exception):
        return "".join(traceback.format_exception(type(err), err, err.__traceback__))
    return format_error_message(err)
