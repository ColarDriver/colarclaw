"""Auto-reply commands args — ported from bk/src/auto-reply/commands-args.ts."""
from __future__ import annotations

import json
from typing import Any, Callable

CommandArgsFormatter = Callable[[dict[str, Any]], str | None]


def _normalize_arg_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
    elif isinstance(value, (int, float, bool)):
        text = str(value).strip()
    else:
        text = json.dumps(value)
    return text if text else None


def _format_set_unset_action(action: str, path: str | None, value: str | None) -> str:
    if action == "unset":
        return f"unset {path}" if path else "unset"
    if action == "set":
        if not path:
            return "set"
        if not value:
            return f"set {path}"
        return f"set {path}={value}"
    return action


def _format_action_args(values: dict[str, Any], format_known: Callable[[str, str | None], str | None]) -> str | None:
    action = (_normalize_arg_value(values.get("action")) or "").lower()
    path = _normalize_arg_value(values.get("path"))
    value = _normalize_arg_value(values.get("value"))
    if not action:
        return None
    known = format_known(action, path)
    if known:
        return known
    return _format_set_unset_action(action, path, value)


def _format_config_args(values: dict[str, Any]) -> str | None:
    def fmt(action: str, path: str | None) -> str | None:
        if action in ("show", "get"):
            return f"{action} {path}" if path else action
        return None
    return _format_action_args(values, fmt)


def _format_debug_args(values: dict[str, Any]) -> str | None:
    def fmt(action: str, _path: str | None) -> str | None:
        return action if action in ("show", "reset") else None
    return _format_action_args(values, fmt)


def _format_queue_args(values: dict[str, Any]) -> str | None:
    parts = []
    for key in ("mode", "debounce", "cap", "drop"):
        v = _normalize_arg_value(values.get(key))
        if v:
            parts.append(f"{key}:{v}" if key != "mode" else v)
    return " ".join(parts) if parts else None


def _format_exec_args(values: dict[str, Any]) -> str | None:
    parts = []
    for key in ("host", "security", "ask", "node"):
        v = _normalize_arg_value(values.get(key))
        if v:
            parts.append(f"{key}={v}")
    return " ".join(parts) if parts else None


COMMAND_ARG_FORMATTERS: dict[str, CommandArgsFormatter] = {
    "config": _format_config_args,
    "debug": _format_debug_args,
    "queue": _format_queue_args,
    "exec": _format_exec_args,
}
