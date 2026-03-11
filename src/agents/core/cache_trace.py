"""Cache trace — ported from bk/src/agents/cache-trace.ts.

Diagnostic tracing for LLM cache interactions. Records session/prompt
state at various stages (loaded, sanitized, limited, before/after prompt)
into JSONL log files with message fingerprinting and redaction.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

log = logging.getLogger("openclaw.agents.cache_trace")

CacheTraceStage = Literal[
    "session:loaded",
    "session:sanitized",
    "session:limited",
    "prompt:before",
    "prompt:images",
    "stream:context",
    "session:after",
]


@dataclass
class CacheTraceConfig:
    enabled: bool = False
    file_path: str = ""
    include_messages: bool = True
    include_prompt: bool = True
    include_system: bool = True


@dataclass
class CacheTraceEvent:
    ts: str
    seq: int
    stage: CacheTraceStage
    run_id: str | None = None
    session_id: str | None = None
    session_key: str | None = None
    provider: str | None = None
    model_id: str | None = None
    workspace_dir: str | None = None
    prompt: str | None = None
    system: Any = None
    options: dict[str, Any] | None = None
    model: dict[str, Any] | None = None
    messages: list[Any] | None = None
    message_count: int | None = None
    message_roles: list[str | None] | None = None
    message_fingerprints: list[str] | None = None
    messages_digest: str | None = None
    system_digest: str | None = None
    note: str | None = None
    error: str | None = None


def _stable_stringify(value: Any, seen: set[int] | None = None) -> str:
    """Deterministic JSON-like serialization for hashing."""
    if seen is None:
        seen = set()
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return json.dumps(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, bytes):
        import base64
        return json.dumps(base64.b64encode(value).decode())

    obj_id = id(value)
    if obj_id in seen:
        return json.dumps("[Circular]")
    seen.add(obj_id)

    if isinstance(value, list):
        parts = [_stable_stringify(item, seen) for item in value]
        return "[" + ",".join(parts) + "]"
    if isinstance(value, dict):
        keys = sorted(value.keys())
        pairs = [f"{json.dumps(k)}:{_stable_stringify(value[k], seen)}" for k in keys]
        return "{" + ",".join(pairs) + "}"

    return json.dumps(str(value))


def _digest(value: Any) -> str:
    serialized = _stable_stringify(value)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _summarize_messages(messages: list[Any]) -> dict[str, Any]:
    fingerprints = [_digest(msg) for msg in messages]
    return {
        "message_count": len(messages),
        "message_roles": [
            msg.get("role") if isinstance(msg, dict) else None
            for msg in messages
        ],
        "message_fingerprints": fingerprints,
        "messages_digest": _digest("|".join(fingerprints)),
    }


def _redact_image_data(data: Any) -> Any:
    """Redact base64 image data from payloads for diagnostics."""
    if isinstance(data, str):
        if data.startswith("data:image/"):
            return "[REDACTED_IMAGE_DATA]"
        return data
    if isinstance(data, list):
        return [_redact_image_data(item) for item in data]
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            if k in ("data", "image_data", "base64") and isinstance(v, str) and len(v) > 200:
                result[k] = "[REDACTED]"
            else:
                result[k] = _redact_image_data(v)
        return result
    return data


class CacheTrace:
    """Trace recorder for LLM cache interactions."""

    def __init__(
        self,
        config: CacheTraceConfig,
        run_id: str | None = None,
        session_id: str | None = None,
        session_key: str | None = None,
        provider: str | None = None,
        model_id: str | None = None,
        workspace_dir: str | None = None,
    ):
        self.config = config
        self.run_id = run_id
        self.session_id = session_id
        self.session_key = session_key
        self.provider = provider
        self.model_id = model_id
        self.workspace_dir = workspace_dir
        self._seq = 0
        self._file_path = config.file_path

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def record_stage(
        self,
        stage: CacheTraceStage,
        *,
        prompt: str | None = None,
        system: Any = None,
        options: dict[str, Any] | None = None,
        model: dict[str, Any] | None = None,
        messages: list[Any] | None = None,
        note: str | None = None,
        error: str | None = None,
    ) -> None:
        if not self.enabled:
            return

        self._seq += 1
        event: dict[str, Any] = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "seq": self._seq,
            "stage": stage,
        }

        if self.run_id:
            event["runId"] = self.run_id
        if self.session_id:
            event["sessionId"] = self.session_id
        if self.session_key:
            event["sessionKey"] = self.session_key
        if self.provider:
            event["provider"] = self.provider
        if self.model_id:
            event["modelId"] = self.model_id
        if self.workspace_dir:
            event["workspaceDir"] = self.workspace_dir

        if prompt is not None and self.config.include_prompt:
            event["prompt"] = prompt
        if system is not None and self.config.include_system:
            event["system"] = system
            event["systemDigest"] = _digest(system)
        if options is not None:
            event["options"] = _redact_image_data(options)
        if model is not None:
            event["model"] = model

        if messages is not None:
            summary = _summarize_messages(messages)
            event.update(summary)
            if self.config.include_messages:
                event["messages"] = _redact_image_data(messages)

        if note:
            event["note"] = note
        if error:
            event["error"] = error

        self._write_event(event)

    def _write_event(self, event: dict[str, Any]) -> None:
        try:
            os.makedirs(os.path.dirname(self._file_path), exist_ok=True)
            line = json.dumps(event, default=str)
            with open(self._file_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as exc:
            log.debug("Failed to write cache trace event: %s", exc)


def resolve_cache_trace_config(
    config: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
) -> CacheTraceConfig:
    """Resolve cache trace configuration from config + environment."""
    if env is None:
        env = dict(os.environ)

    diag_config = config.get("diagnostics", {}).get("cacheTrace", {}) if config else {}
    env_enabled = env.get("OPENCLAW_CACHE_TRACE", "").lower() in ("1", "true", "yes")
    enabled = env_enabled or diag_config.get("enabled", False)

    file_override = diag_config.get("filePath", "").strip() or env.get("OPENCLAW_CACHE_TRACE_FILE", "").strip()
    if file_override:
        file_path = os.path.expanduser(file_override)
    else:
        state_dir = env.get("OPENCLAW_STATE_DIR", os.path.expanduser("~/.openclaw"))
        file_path = os.path.join(state_dir, "logs", "cache-trace.jsonl")

    def _env_bool(key: str) -> bool | None:
        val = env.get(key, "").lower()
        if val in ("1", "true", "yes"):
            return True
        if val in ("0", "false", "no"):
            return False
        return None

    include_messages = _env_bool("OPENCLAW_CACHE_TRACE_MESSAGES") or diag_config.get("includeMessages", True)
    include_prompt = _env_bool("OPENCLAW_CACHE_TRACE_PROMPT") or diag_config.get("includePrompt", True)
    include_system = _env_bool("OPENCLAW_CACHE_TRACE_SYSTEM") or diag_config.get("includeSystem", True)

    return CacheTraceConfig(
        enabled=enabled,
        file_path=file_path,
        include_messages=bool(include_messages),
        include_prompt=bool(include_prompt),
        include_system=bool(include_system),
    )


def create_cache_trace(
    config: dict[str, Any] | None = None,
    **kwargs: Any,
) -> CacheTrace | None:
    """Create a cache trace recorder if enabled."""
    cfg = resolve_cache_trace_config(config)
    if not cfg.enabled:
        return None
    return CacheTrace(cfg, **kwargs)
