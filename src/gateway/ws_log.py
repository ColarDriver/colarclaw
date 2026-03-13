"""Gateway WS logging — ported from bk/src/gateway/ws-log.ts, ws-logging.ts.

WebSocket message logging with compact/verbose/optimized modes,
inflight tracking, duration measurement, and sensitive value redaction.
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

logger = logging.getLogger("gateway.ws")

# ─── ws-logging.ts ───

DEFAULT_WS_SLOW_MS = 5000

WS_LOG_STYLES = ("auto", "compact", "verbose", "optimized")


def get_gateway_ws_log_style() -> str:
    """Get the configured WS log style."""
    style = os.environ.get("OPENCLAW_WS_LOG_STYLE", "auto").strip().lower()
    return style if style in WS_LOG_STYLES else "auto"


# ─── ws-log.ts ───

LOG_VALUE_LIMIT = 240
UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)

# Inflight tracking
_ws_inflight_compact: dict[str, dict[str, Any]] = {}
_ws_last_compact_conn_id: list[str | None] = [None]  # mutable container
_ws_inflight_optimized: dict[str, float] = {}
_ws_inflight_since: dict[str, float] = {}

# Meta keys to skip in rest meta collection
WS_META_SKIP_KEYS = {"connId", "id", "method", "ok", "event"}


def should_log_ws() -> bool:
    """Check if WS logging is enabled."""
    return logger.isEnabledFor(logging.INFO)


def short_id(value: str) -> str:
    """Shorten a UUID or long ID for display."""
    s = value.strip()
    if UUID_RE.match(s):
        return f"{s[:8]}…{s[-4:]}"
    if len(s) <= 24:
        return s
    return f"{s[:12]}…{s[-4:]}"


def format_for_log(value: Any) -> str:
    """Format a value for log output, with truncation and redaction."""
    try:
        if isinstance(value, Exception):
            parts = []
            if hasattr(value, '__class__'):
                parts.append(value.__class__.__name__)
            msg = str(value)
            if msg:
                parts.append(msg)
            combined = ": ".join(filter(None, parts)).strip()
            if combined:
                return combined[:LOG_VALUE_LIMIT] + "..." if len(combined) > LOG_VALUE_LIMIT else combined

        if isinstance(value, dict):
            msg = value.get("message", "")
            if isinstance(msg, str) and msg.strip():
                name = value.get("name", "")
                parts = [name, msg.strip()] if name else [msg.strip()]
                code = value.get("code", "")
                if code:
                    parts.append(f"code={code}")
                combined = ": ".join(filter(None, parts)).strip()
                return combined[:LOG_VALUE_LIMIT] + "..." if len(combined) > LOG_VALUE_LIMIT else combined

        if isinstance(value, (str, int, float)):
            s = str(value)
        else:
            import json
            s = json.dumps(value, default=str)

        if not s:
            return ""
        # Basic sensitive value redaction
        s = _redact_sensitive(s)
        return s[:LOG_VALUE_LIMIT] + "..." if len(s) > LOG_VALUE_LIMIT else s
    except Exception:
        return str(value)


def _redact_sensitive(text: str) -> str:
    """Basic sensitive value redaction."""
    # Redact bearer tokens
    text = re.sub(r'(Bearer\s+)\S+', r'\1[REDACTED]', text, flags=re.I)
    # Redact API keys
    text = re.sub(r'(sk-[a-zA-Z0-9]{4})[a-zA-Z0-9]+', r'\1[REDACTED]', text)
    return text


def _compact_preview(text: str, max_len: int = 160) -> str:
    """Create a compact preview of text."""
    one_line = re.sub(r'\s+', ' ', text).strip()
    if len(one_line) <= max_len:
        return one_line
    return f"{one_line[:max_len - 1]}…"


def _collect_rest_meta(meta: dict[str, Any] | None) -> list[str]:
    """Collect non-standard meta fields for log display."""
    if not meta:
        return []
    parts = []
    for key, value in meta.items():
        if value is None:
            continue
        if key in WS_META_SKIP_KEYS:
            continue
        parts.append(f"{key}={format_for_log(value)}")
    return parts


def summarize_agent_event_for_ws_log(payload: Any) -> dict[str, Any]:
    """Summarize an agent event payload for WS logging."""
    if not payload or not isinstance(payload, dict):
        return {}

    run_id = payload.get("runId")
    stream = payload.get("stream")
    seq = payload.get("seq")
    session_key = payload.get("sessionKey")
    data = payload.get("data", {})

    extra: dict[str, Any] = {}
    if isinstance(run_id, str) and run_id:
        extra["run"] = short_id(run_id)
    if isinstance(session_key, str) and session_key:
        extra["session"] = session_key
    if isinstance(stream, str) and stream:
        extra["stream"] = stream
    if isinstance(seq, int):
        extra["aseq"] = seq

    if not isinstance(data, dict):
        return extra

    if stream == "assistant":
        text = data.get("text")
        if isinstance(text, str) and text.strip():
            extra["text"] = _compact_preview(text)
        media_urls = data.get("mediaUrls")
        if isinstance(media_urls, list) and media_urls:
            extra["media"] = len(media_urls)
        return extra

    if stream == "tool":
        phase = data.get("phase")
        name = data.get("name")
        if phase or name:
            extra["tool"] = f"{phase or '?'}:{name or '?'}"
        tool_call_id = data.get("toolCallId")
        if isinstance(tool_call_id, str) and tool_call_id:
            extra["call"] = short_id(tool_call_id)
        meta = data.get("meta")
        if isinstance(meta, str) and meta.strip():
            extra["meta"] = meta
        if isinstance(data.get("isError"), bool):
            extra["err"] = data["isError"]
        return extra

    if stream == "lifecycle":
        phase = data.get("phase")
        if isinstance(phase, str):
            extra["phase"] = phase
        if isinstance(data.get("aborted"), bool):
            extra["aborted"] = data["aborted"]
        error = data.get("error")
        if isinstance(error, str) and error.strip():
            extra["error"] = _compact_preview(error, 120)
        return extra

    reason = data.get("reason")
    if isinstance(reason, str) and reason.strip():
        extra["reason"] = reason
    return extra


def log_ws(direction: str, kind: str, meta: dict[str, Any] | None = None) -> None:
    """Log a WebSocket message with appropriate formatting.

    Args:
        direction: "in" or "out"
        kind: "req", "res", "event", "parse-error"
        meta: Optional metadata (connId, id, method, ok, event, etc.)
    """
    if not should_log_ws():
        return

    style = get_gateway_ws_log_style()
    verbose = os.environ.get("OPENCLAW_VERBOSE") == "1"

    if not verbose:
        _log_ws_optimized(direction, kind, meta)
        return

    if style in ("compact", "auto"):
        _log_ws_compact(direction, kind, meta)
        return

    # Verbose mode
    now = time.time()
    conn_id = meta.get("connId", "") if meta else ""
    req_id = meta.get("id", "") if meta else ""
    method = meta.get("method", "") if meta else ""
    ok = meta.get("ok") if meta else None
    event = meta.get("event", "") if meta else ""

    inflight_key = f"{conn_id}:{req_id}" if conn_id and req_id else None

    # Track inflight for duration measurement
    if direction == "in" and kind == "req" and inflight_key:
        _ws_inflight_since[inflight_key] = now

    duration_ms: int | None = None
    if direction == "out" and kind == "res" and inflight_key:
        started_at = _ws_inflight_since.pop(inflight_key, None)
        if started_at:
            duration_ms = int((now - started_at) * 1000)

    # Build log line
    dir_arrow = "←" if direction == "in" else "→"
    headline = method if kind in ("req", "res") else event if kind == "event" else ""
    status = ""
    if kind == "res" and ok is not None:
        status = "✓" if ok else "✗"
    duration_str = f" {duration_ms}ms" if duration_ms is not None else ""

    rest_meta = _collect_rest_meta(meta)
    trailing = []
    if conn_id:
        trailing.append(f"conn={short_id(conn_id)}")
    if req_id:
        trailing.append(f"id={short_id(req_id)}")

    parts = [f"{dir_arrow} {kind}", status, headline, duration_str]
    parts.extend(rest_meta)
    parts.extend(trailing)
    logger.info(" ".join(filter(None, parts)))


def _log_ws_optimized(direction: str, kind: str, meta: dict[str, Any] | None = None) -> None:
    """Optimized WS logging: only log errors and slow responses."""
    conn_id = meta.get("connId", "") if meta else ""
    req_id = meta.get("id", "") if meta else ""
    ok = meta.get("ok") if meta else None
    method = meta.get("method", "") if meta else ""

    inflight_key = f"{conn_id}:{req_id}" if conn_id and req_id else None

    if direction == "in" and kind == "req" and inflight_key:
        _ws_inflight_optimized[inflight_key] = time.time()
        if len(_ws_inflight_optimized) > 2000:
            _ws_inflight_optimized.clear()
        return

    if kind == "parse-error":
        error_msg = format_for_log(meta.get("error", "")) if meta else ""
        logger.warning(f"✗ parse-error {error_msg} conn={short_id(conn_id or '?')}")
        return

    if direction != "out" or kind != "res":
        return

    started_at = _ws_inflight_optimized.pop(inflight_key, None) if inflight_key else None
    duration_ms = int((time.time() - started_at) * 1000) if started_at else None

    should_log = (ok is False) or (duration_ms is not None and duration_ms >= DEFAULT_WS_SLOW_MS)
    if not should_log:
        return

    status = "✓" if ok else "✗" if ok is not None else ""
    duration_str = f" {duration_ms}ms" if duration_ms is not None else ""
    logger.info(f"⇄ res {status} {method}{duration_str} conn={short_id(conn_id or '?')}")


def _log_ws_compact(direction: str, kind: str, meta: dict[str, Any] | None = None) -> None:
    """Compact WS logging: collapsed request/response pairs."""
    now = time.time()
    conn_id = meta.get("connId", "") if meta else ""
    req_id = meta.get("id", "") if meta else ""
    method = meta.get("method", "") if meta else ""
    ok = meta.get("ok") if meta else None
    event = meta.get("event", "") if meta else ""
    inflight_key = f"{conn_id}:{req_id}" if conn_id and req_id else None

    if kind == "req" and direction == "in" and inflight_key:
        _ws_inflight_compact[inflight_key] = {"ts": now, "method": method, "meta": meta}
        return

    arrow = "⇄" if kind in ("req", "res") else ("←" if direction == "in" else "→")
    status = ""
    if kind == "res" and ok is not None:
        status = "✓" if ok else "✗"

    started_at = None
    if kind == "res" and direction == "out" and inflight_key:
        entry = _ws_inflight_compact.pop(inflight_key, None)
        started_at = entry.get("ts") if entry else None
    duration_ms = int((now - started_at) * 1000) if started_at else None
    duration_str = f" {duration_ms}ms" if duration_ms is not None else ""

    headline = method if kind in ("req", "res") else event if kind == "event" else ""
    rest_meta = _collect_rest_meta(meta)

    trailing = []
    if conn_id and conn_id != _ws_last_compact_conn_id[0]:
        trailing.append(f"conn={short_id(conn_id)}")
        _ws_last_compact_conn_id[0] = conn_id
    if req_id:
        trailing.append(f"id={short_id(req_id)}")

    parts = [f"{arrow} {kind}", status, headline, duration_str]
    parts.extend(rest_meta)
    parts.extend(trailing)
    logger.info(" ".join(filter(None, parts)))
