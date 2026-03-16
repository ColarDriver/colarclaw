from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from ...config.io import read_config_file, write_config_file
from ...config.paths import resolve_config_path
from ...core.auth import AuthContext, _decode_token, resolve_websocket_auth
from ...core.config import load_settings
from ...llm.providers import (
    canonical_provider_id,
    list_custom_provider_protocols,
    list_provider_aliases,
    list_registered_provider_ids,
    provider_api_protocol,
)
from ...models.registry import parse_registered_model_entries
from ...version import get_version

router = APIRouter(tags=["ws"])

SUPPORTED_METHODS = [
    "connect",
    "status",
    "health",
    "last-heartbeat",
    "models.list",
    "models.providers.get",
    "models.providers.apply",
    "models.providers.delete",
    "chat.history",
    "chat.send",
    "chat.abort",
    "sessions.list",
    "sessions.patch",
    "sessions.delete",
    "sessions.reset",
    "sessions.compact",
    "system-presence",
    "agents.list",
    "agent.identity.get",
    "agents.files.list",
    "agents.files.get",
    "agents.files.set",
    "node.list",
    "device.pair.list",
    "device.pair.approve",
    "device.pair.reject",
    "device.token.rotate",
    "device.token.revoke",
    "logs.tail",
    "config.get",
    "config.schema",
    "config.set",
    "config.apply",
    "config.openFile",
    "channels.status",
    "channels.logout",
    "web.login.start",
    "web.login.wait",
    "skills.status",
    "skills.update",
    "skills.install",
    "tools.catalog",
    "cron.status",
    "cron.list",
    "cron.runs",
    "cron.add",
    "cron.update",
    "cron.remove",
    "cron.run",
    "exec.approvals.get",
    "exec.approvals.set",
    "exec.approvals.node.get",
    "exec.approvals.node.set",
    "exec.approval.resolve",
    "sessions.usage",
    "usage.cost",
    "sessions.usage.timeseries",
    "sessions.usage.logs",
    "update.run",
]

_BUILTIN_PROVIDER_IDS = tuple(
    list_registered_provider_ids(include_aliases=False, include_echo=False)
)
_BUILTIN_PROVIDER_ID_SET = set(_BUILTIN_PROVIDER_IDS)
_PROVIDER_ALIASES = list_provider_aliases()
_ALLOWED_CUSTOM_PROVIDER_APIS = set(list_custom_provider_protocols())
_PROVIDER_LABELS: dict[str, str] = {
    "amazon-bedrock": "Amazon Bedrock",
    "anyscale": "Anyscale",
    "anthropic": "Anthropic",
    "azure": "Azure OpenAI",
    "byteplus": "BytePlus",
    "cloudflare-ai-gateway": "Cloudflare AI Gateway",
    "fireworks": "Fireworks AI",
    "google": "Google Gemini",
    "groq": "Groq",
    "huggingface": "Hugging Face",
    "kimi-coding": "Kimi Coding",
    "nvidia": "NVIDIA NIM",
    "ollama": "Ollama",
    "opencode": "OpenCode",
    "openai": "OpenAI",
    "openrouter": "OpenRouter",
    "perplexity": "Perplexity",
    "qwen-portal": "Qwen Portal",
    "together": "Together AI",
    "vercel-ai-gateway": "Vercel AI Gateway",
    "volcengine": "Volcengine",
    "zai": "Z.ai",
}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _as_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _as_text(value: object, default: str = "") -> str:
    if isinstance(value, str):
        return value.strip()
    return default


def _as_scope_list(value: object, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return fallback
    scopes: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        scope = item.strip()
        if not scope or scope in seen:
            continue
        seen.add(scope)
        scopes.append(scope)
    return scopes or fallback


def _res_ok(req_id: str, payload: object = None) -> dict[str, object]:
    frame: dict[str, object] = {"type": "res", "id": req_id, "ok": True}
    if payload is not None:
        frame["payload"] = payload
    return frame


def _res_error(
    req_id: str,
    code: str,
    message: str,
    *,
    details: object | None = None,
) -> dict[str, object]:
    err: dict[str, object] = {"code": code, "message": message}
    if details is not None:
        err["details"] = details
    return {"type": "res", "id": req_id, "ok": False, "error": err}


def _hash_json_payload(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def _split_model_key(model_key: str) -> tuple[str, str]:
    if "/" in model_key:
        provider, model = model_key.split("/", 1)
        provider_key = provider.strip().lower() or "openai"
        model_id = model.strip() or model_key
        return provider_key, model_id
    return "openai", model_key


def _parse_agent_id_from_session_key(session_key: str) -> str:
    raw = session_key.strip().lower()
    parts = raw.split(":")
    if len(parts) >= 3 and parts[0] == "agent" and parts[1].strip():
        return parts[1].strip()
    return "main"


def _session_kind_for_key(session_key: str) -> str:
    lowered = session_key.strip().lower()
    if lowered == "main":
        return "global"
    if ":group:" in lowered:
        return "group"
    if ":direct:" in lowered or ":dm:" in lowered:
        return "direct"
    return "unknown"


def _build_assistant_message(text: str) -> dict[str, object]:
    return {
        "role": "assistant",
        "text": text,
        "content": [{"type": "text", "text": text}],
        "timestamp": _now_ms(),
    }


def _empty_usage_totals() -> dict[str, object]:
    return {
        "input": 0,
        "output": 0,
        "cacheRead": 0,
        "cacheWrite": 0,
        "totalTokens": 0,
        "totalCost": 0,
    }


def _empty_usage_aggregates() -> dict[str, object]:
    return {
        "messages": {
            "total": 0,
            "user": 0,
            "assistant": 0,
            "toolCalls": 0,
            "toolResults": 0,
            "errors": 0,
        },
        "tools": {"totalCalls": 0, "uniqueTools": 0, "tools": []},
        "byModel": [],
        "byProvider": [],
        "byAgent": [],
        "byChannel": [],
        "dailyLatency": [],
        "modelDaily": [],
        "daily": [],
    }


async def _send_frame(
    websocket: WebSocket,
    send_lock: asyncio.Lock,
    frame: dict[str, object],
) -> bool:
    try:
        async with send_lock:
            await websocket.send_json(frame)
        return True
    except Exception:
        return False


def _get_session_meta_store(websocket: WebSocket) -> dict[str, dict[str, object]]:
    store = getattr(websocket.app.state, "session_meta", None)
    if isinstance(store, dict):
        return store
    next_store: dict[str, dict[str, object]] = {}
    websocket.app.state.session_meta = next_store
    return next_store


def _get_agent_files_store(websocket: WebSocket) -> dict[str, dict[str, str]]:
    store = getattr(websocket.app.state, "agent_files_store", None)
    if isinstance(store, dict):
        return store
    next_store: dict[str, dict[str, str]] = {}
    websocket.app.state.agent_files_store = next_store
    return next_store


def _get_skill_entries_store(websocket: WebSocket) -> dict[str, dict[str, object]]:
    """Per-skill config store: dict[skillKey -> {enabled: bool, apiKey: str, ...}].
    Absence of a key means the skill uses its default state (enabled).
    Mirrors openclaw's skills.entries[skillKey] config structure.
    On first access, loads persisted entries from the config file.
    """
    store = getattr(websocket.app.state, "skill_entries_store", None)
    if isinstance(store, dict):
        return store
    # Load persisted skill entries from config file
    next_store: dict[str, dict[str, object]] = {}
    try:
        config_path = resolve_config_path()
        loaded = read_config_file(config_path)
        if isinstance(loaded, dict):
            skills_section = loaded.get("skills")
            if isinstance(skills_section, dict):
                entries = skills_section.get("entries")
                if isinstance(entries, dict):
                    for key, val in entries.items():
                        if isinstance(val, dict):
                            next_store[str(key)] = dict(val)
    except Exception:
        pass
    websocket.app.state.skill_entries_store = next_store
    return next_store


def _get_exec_approvals_store(websocket: WebSocket) -> dict[str, dict[str, object]]:
    store = getattr(websocket.app.state, "exec_approvals_store", None)
    if isinstance(store, dict):
        return store
    next_store: dict[str, dict[str, object]] = {"gateway": {"version": 1}}
    websocket.app.state.exec_approvals_store = next_store
    return next_store


def _get_control_ui_config_store(websocket: WebSocket) -> dict[str, object]:
    store = getattr(websocket.app.state, "control_ui_config_store", None)
    if isinstance(store, dict):
        return store
    container = websocket.app.state.container
    default_model = str(container.runtime_config.get("defaultModel", "")).strip()
    next_store: dict[str, object] = {
        "models": {
            "default": default_model,
            "fallback": list(container.runtime_config.get("fallbackModels") or ()),
        },
        "tools": {
            "allowlist": list(container.runtime_config.get("toolAllowlist") or ()),
            "denylist": list(container.runtime_config.get("toolDenylist") or ()),
        },
        "skills": {
            "enabled": list(container.runtime_config.get("skillsEnabled") or ()),
        },
    }
    websocket.app.state.control_ui_config_store = next_store
    return next_store


def _get_log_buffer(websocket: WebSocket) -> list[str]:
    logs = getattr(websocket.app.state, "gateway_log_buffer", None)
    if isinstance(logs, list):
        return logs
    seeded = [
        json.dumps(
            {
                "time": _utc_iso_now(),
                "message": "Python gateway compatibility websocket ready",
                "_meta": {"logLevelName": "info", "name": "gateway.ws"},
            }
        )
    ]
    websocket.app.state.gateway_log_buffer = seeded
    return seeded


def _append_gateway_log(websocket: WebSocket, message: str, level: str = "info") -> None:
    logs = _get_log_buffer(websocket)
    logs.append(
        json.dumps(
            {
                "time": _utc_iso_now(),
                "message": message,
                "_meta": {"logLevelName": level, "name": "gateway.ws"},
            }
        )
    )
    if len(logs) > 500:
        del logs[:-500]


def _validate_requested_model(container, model: object) -> str | None:
    if model is None:
        return None
    if not isinstance(model, str):
        raise ValueError("model must be string")
    value = model.strip()
    if not value:
        return None
    if container.model_registry.keys() and not container.model_registry.has(value):
        raise ValueError(f"model not registered: {value}")
    return value


async def _load_graph_session_messages(container, session_key: str) -> list[dict[str, str]]:
    messages = await container.session_repo.list_messages(session_key)
    recent = messages[-40:]
    return [{"role": msg.role, "content": msg.text} for msg in recent]


async def _collect_session_rows(
    websocket: WebSocket,
    *,
    active_minutes: int = 0,
    limit: int = 0,
) -> tuple[list[dict[str, object]], int]:
    container = websocket.app.state.container
    meta_store = _get_session_meta_store(websocket)
    now = _now_ms()
    sessions = await container.session_repo.list_sessions()
    by_id = {entry.id: entry for entry in sessions}
    session_keys = set(by_id.keys()) | set(meta_store.keys())
    session_keys.add("main")

    rows: list[dict[str, object]] = []
    for key in session_keys:
        record = by_id.get(key)
        meta = meta_store.get(key, {})
        updated_at = record.updated_at_ms if record is not None else _as_int(meta.get("updatedAt"))
        if active_minutes > 0 and updated_at is not None:
            age_ms = max(0, now - updated_at)
            if age_ms > active_minutes * 60_000:
                continue
        label = _as_text(meta.get("label"), record.title if record is not None else "")
        model = _as_text(meta.get("model"))
        provider = _as_text(meta.get("modelProvider"))
        if model and not provider:
            provider, _ = _split_model_key(model)
        row: dict[str, object] = {
            "key": key,
            "kind": _session_kind_for_key(key),
            "label": label or None,
            "displayName": label or key,
            "updatedAt": updated_at,
            "sessionId": key,
            "thinkingLevel": _as_text(meta.get("thinkingLevel")) or None,
            "fastMode": _as_bool(meta.get("fastMode")),
            "verboseLevel": _as_text(meta.get("verboseLevel")) or None,
            "reasoningLevel": _as_text(meta.get("reasoningLevel")) or None,
            "model": model or None,
            "modelProvider": provider or None,
            "contextTokens": _as_int(meta.get("contextTokens")),
        }
        rows.append(row)

    rows.sort(
        key=lambda item: (
            item.get("updatedAt") is None,
            -(item.get("updatedAt") or 0),
            str(item.get("key") or ""),
        )
    )
    total = len(rows)
    if limit > 0:
        rows = rows[:limit]
    return rows, total


async def _build_health_summary(websocket: WebSocket) -> dict[str, object]:
    rows, total = await _collect_session_rows(websocket, limit=5)
    now = _now_ms()
    recent = [
        {
            "key": row.get("key"),
            "updatedAt": row.get("updatedAt"),
            "age": None
            if row.get("updatedAt") is None
            else max(0, now - int(row["updatedAt"])),  # type: ignore[index]
        }
        for row in rows
    ]
    return {
        "ok": True,
        "ts": now,
        "durationMs": 1,
        "heartbeatSeconds": 10,
        "defaultAgentId": "main",
        "agents": [{"id": "main", "name": "Assistant"}],
        "sessions": {
            "path": "memory://sessions",
            "count": total,
            "recent": recent,
        },
    }


async def _build_status_summary(websocket: WebSocket, conn_id: str) -> dict[str, object]:
    rows, total = await _collect_session_rows(websocket, limit=0)
    return {
        "status": "ok",
        "ts": _now_ms(),
        "serverVersion": get_version(),
        "connId": conn_id,
        "sessionCount": total,
        "modelCount": len(websocket.app.state.container.model_registry.list()),
        "sessions": rows[:10],
    }


def _build_model_catalog(container) -> list[dict[str, object]]:
    entries = []
    seen: set[str] = set()
    for model in container.model_registry.list():
        model_id = f"{model.provider}/{model.id}"
        seen.add(model_id)
        entries.append(
            {
                "id": model_id,
                "name": model.name or model.id,
                "provider": model.provider,
                "contextWindow": model.context_window,
                "reasoning": bool(model.reasoning),
                "input": ["text"],
            }
        )
    default_model = str(container.runtime_config.get("defaultModel", "")).strip()
    if default_model and default_model not in seen:
        provider, model_id = _split_model_key(default_model)
        entries.append(
            {
                "id": default_model,
                "name": model_id,
                "provider": provider,
                "contextWindow": None,
                "reasoning": False,
                "input": ["text"],
            }
        )
    return entries


def _provider_kind(provider_id: str) -> str:
    return "builtin" if provider_id in _BUILTIN_PROVIDER_ID_SET else "custom"


def _provider_label(provider_id: str) -> str:
    known = _PROVIDER_LABELS.get(provider_id)
    if known:
        return known
    if not provider_id:
        return "Provider"
    parts = [segment for segment in provider_id.split("-") if segment]
    if not parts:
        return provider_id
    return " ".join(part[:1].upper() + part[1:] for part in parts)


def _normalize_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = ""
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            if isinstance(item.get("id"), str):
                text = item.get("id", "").strip()
            elif isinstance(item.get("key"), str):
                text = item.get("key", "").strip()
        if not text:
            continue
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _registry_model_key(entry: object) -> str:
    if not isinstance(entry, str):
        return ""
    value = entry.strip()
    if not value:
        return ""
    if "=" in value:
        value = value.split("=", 1)[0].strip()
    return value


def _ensure_registry_contains_models(
    model_registry: list[str],
    model_keys: list[str],
) -> list[str]:
    registry = _normalize_string_list(model_registry)
    seen = {key for key in (_registry_model_key(item) for item in registry) if key}
    for key in model_keys:
        model_key = _as_text(key)
        if not model_key or model_key in seen:
            continue
        registry.append(model_key)
        seen.add(model_key)
    return registry


def _looks_like_url(value: str) -> bool:
    text = value.strip().lower()
    if not text:
        return False
    return text.startswith("http://") or text.startswith("https://") or "://" in text


def _mask_api_key(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    if len(text) <= 6:
        return "*" * len(text)
    hidden_len = max(4, len(text) - 6)
    return f"{text[:3]}{'*' * hidden_len}{text[-3:]}"


def _normalize_provider_configs(raw: object) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, dict[str, Any]] = {}
    for raw_provider_id, raw_entry in raw.items():
        if not isinstance(raw_provider_id, str) or not isinstance(raw_entry, dict):
            continue
        provider_id = canonical_provider_id(raw_provider_id)
        if not provider_id or provider_id == "echo":
            continue
        entry: dict[str, Any] = {}
        if "api" in raw_entry:
            api = _as_text(raw_entry.get("api")).lower()
            if api:
                entry["api"] = api
        if "baseUrl" in raw_entry:
            base_url = _as_text(raw_entry.get("baseUrl"))
            if base_url:
                entry["baseUrl"] = base_url
        if "apiKey" in raw_entry:
            api_key = _as_text(raw_entry.get("apiKey"))
            if api_key:
                entry["apiKey"] = api_key
        models = _normalize_string_list(raw_entry.get("models"))
        if models:
            entry["models"] = models
        if _provider_kind(provider_id) == "custom":
            api = _as_text(entry.get("api")).lower()
            if api not in _ALLOWED_CUSTOM_PROVIDER_APIS:
                entry["api"] = "openai-completions"
        elif "api" in entry:
            # Builtin providers use a fixed runtime protocol family.
            entry["api"] = provider_api_protocol(provider_id)
        if entry and _provider_entry_has_data(provider_id, entry):
            normalized[provider_id] = entry
    return normalized


def _provider_entry_has_data(provider_id: str, entry: dict[str, Any]) -> bool:
    if _as_text(entry.get("apiKey")):
        return True
    if _as_text(entry.get("baseUrl")):
        return True
    if _normalize_string_list(entry.get("models")):
        return True
    if _provider_kind(provider_id) == "custom" and _as_text(entry.get("api")):
        return True
    return False


def _coerce_provider_apply_entries(value: object) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            provider_id = _as_text(item.get("id")).lower()
            if not provider_id:
                continue
            entries[provider_id] = dict(item)
        return entries
    if isinstance(value, dict):
        for key, raw in value.items():
            if not isinstance(key, str) or not isinstance(raw, dict):
                continue
            entry = dict(raw)
            if "id" not in entry:
                entry["id"] = key
            entries[key.strip().lower()] = entry
    return entries


def _merge_provider_configs(
    existing: dict[str, dict[str, Any]],
    incoming: object,
) -> dict[str, dict[str, Any]]:
    if incoming is None:
        return _normalize_provider_configs(existing)

    merged: dict[str, dict[str, Any]] = {
        provider_id: dict(entry) for provider_id, entry in existing.items()
    }
    apply_entries = _coerce_provider_apply_entries(incoming)
    for raw_provider_id, patch in apply_entries.items():
        provider_id = canonical_provider_id(raw_provider_id)
        if not provider_id or provider_id == "echo":
            continue
        next_entry = dict(merged.get(provider_id, {}))

        if "baseUrl" in patch:
            base_url = _as_text(patch.get("baseUrl"))
            if base_url:
                next_entry["baseUrl"] = base_url
            else:
                next_entry.pop("baseUrl", None)

        if "models" in patch:
            models = _normalize_string_list(patch.get("models"))
            if models:
                next_entry["models"] = models
            else:
                next_entry.pop("models", None)

        if "apiKey" in patch:
            raw_key = patch.get("apiKey")
            if isinstance(raw_key, str):
                api_key = raw_key.strip()
                if api_key:
                    if _looks_like_url(api_key):
                        raise ValueError(
                            f"apiKey for provider '{provider_id}' looks like a URL; paste only the key value"
                        )
                    next_entry["apiKey"] = api_key
                else:
                    next_entry.pop("apiKey", None)

        if "api" in patch:
            api = _as_text(patch.get("api")).lower()
            if api:
                next_entry["api"] = api
            else:
                next_entry.pop("api", None)

        if _provider_kind(provider_id) == "custom":
            api = _as_text(next_entry.get("api")).lower() or "openai-completions"
            if api not in _ALLOWED_CUSTOM_PROVIDER_APIS:
                raise ValueError(
                    f"unsupported custom provider api for {provider_id}: {api}"
                )
            next_entry["api"] = api
        elif "api" in next_entry:
            next_entry["api"] = provider_api_protocol(provider_id)

        if _provider_entry_has_data(provider_id, next_entry):
            merged[provider_id] = next_entry
        else:
            merged.pop(provider_id, None)

    return _normalize_provider_configs(merged)


def _provider_entry_for_response(provider_id: str, entry: dict[str, Any]) -> dict[str, Any]:
    api_key = _as_text(entry.get("apiKey"))
    return {
        "id": provider_id,
        "label": _provider_label(provider_id),
        "kind": _provider_kind(provider_id),
        "api": _as_text(entry.get("api")) or provider_api_protocol(provider_id, entry),
        "baseUrl": _as_text(entry.get("baseUrl")),
        "models": _normalize_string_list(entry.get("models")),
        "apiKeyConfigured": bool(api_key),
        "apiKeyPreview": _mask_api_key(api_key),
    }


def _catalog_entry_for_provider(provider_id: str) -> dict[str, Any]:
    return {
        "id": provider_id,
        "label": _provider_label(provider_id),
        "kind": "builtin",
        "api": provider_api_protocol(provider_id),
        "aliases": list(_PROVIDER_ALIASES.get(provider_id, ())),
    }


def _extract_defaults_from_config(
    config: dict[str, Any],
    *,
    runtime_default_model: str,
    runtime_fallback_models: list[str],
) -> tuple[str, list[str]]:
    default_model = runtime_default_model
    fallback_models = list(runtime_fallback_models)
    agents = config.get("agents")
    if not isinstance(agents, dict):
        return default_model, fallback_models
    defaults = agents.get("defaults")
    if not isinstance(defaults, dict):
        return default_model, fallback_models

    raw_model = defaults.get("model")
    if isinstance(raw_model, str) and raw_model.strip():
        default_model = raw_model.strip()
    elif isinstance(raw_model, dict):
        primary = _as_text(raw_model.get("primary"))
        if primary:
            default_model = primary
        if isinstance(raw_model.get("fallbacks"), list):
            fallback_models = _normalize_string_list(raw_model.get("fallbacks"))

    if "fallbackModels" in defaults and isinstance(defaults.get("fallbackModels"), list):
        fallback_models = _normalize_string_list(defaults.get("fallbackModels"))

    return default_model, fallback_models


def _extract_model_registry_from_config(
    config: dict[str, Any],
    *,
    runtime_model_registry: list[str],
) -> list[str]:
    models = config.get("models")
    if not isinstance(models, dict):
        return list(runtime_model_registry)
    if "registry" in models and isinstance(models.get("registry"), list):
        return _normalize_string_list(models.get("registry"))
    return list(runtime_model_registry)


def _extract_provider_configs_from_config(
    config: dict[str, Any],
    *,
    runtime_provider_configs: object,
) -> dict[str, dict[str, Any]]:
    models = config.get("models")
    if isinstance(models, dict):
        if "providers" in models and isinstance(models.get("providers"), dict):
            return _normalize_provider_configs(models.get("providers"))
    return _normalize_provider_configs(runtime_provider_configs)


def _load_models_provider_state(container) -> tuple[str, dict[str, Any], dict[str, Any]]:
    config_path = resolve_config_path()
    config_data: dict[str, Any] = {}
    try:
        loaded = read_config_file(config_path)
        if isinstance(loaded, dict):
            config_data = loaded
    except FileNotFoundError:
        config_data = {}
    except Exception:
        # Keep runtime operable even if config parse fails.
        config_data = {}

    runtime_default_model = _as_text(container.runtime_config.get("defaultModel"))
    runtime_fallback_models = _normalize_string_list(
        list(container.runtime_config.get("fallbackModels", ()))
    )
    runtime_model_registry = _normalize_string_list(
        list(container.runtime_config.get("modelRegistry", ()))
    )
    runtime_provider_configs = container.runtime_config.get("providerConfigs", {})

    default_model, fallback_models = _extract_defaults_from_config(
        config_data,
        runtime_default_model=runtime_default_model,
        runtime_fallback_models=runtime_fallback_models,
    )
    model_registry = _extract_model_registry_from_config(
        config_data,
        runtime_model_registry=runtime_model_registry,
    )
    model_registry = _ensure_registry_contains_models(
        model_registry,
        [default_model, *fallback_models],
    )
    provider_configs = _extract_provider_configs_from_config(
        config_data,
        runtime_provider_configs=runtime_provider_configs,
    )

    state = {
        "defaultModel": default_model,
        "fallbackModels": fallback_models,
        "modelRegistry": model_registry,
        "providerConfigs": provider_configs,
    }
    return config_path, config_data, state


def _apply_models_provider_runtime(container, state: dict[str, Any]) -> None:
    default_model = _as_text(state.get("defaultModel"))
    fallback_models = tuple(_normalize_string_list(state.get("fallbackModels")))
    model_registry = tuple(
        _ensure_registry_contains_models(
            _normalize_string_list(state.get("modelRegistry")),
            [default_model, *fallback_models],
        )
    )
    provider_configs = _normalize_provider_configs(state.get("providerConfigs"))

    container.runtime_config["defaultModel"] = default_model
    container.runtime_config["fallbackModels"] = fallback_models
    container.runtime_config["modelRegistry"] = model_registry
    container.runtime_config["providerConfigs"] = provider_configs

    container.model_registry.replace(parse_registered_model_entries(model_registry))
    container.llm_router.update_models(
        default_model=default_model,
        fallback_models=fallback_models,
    )
    container.llm_router.update_provider_configs(provider_configs)


def _persist_models_provider_state(
    *,
    config_path: str,
    config_data: dict[str, Any],
    state: dict[str, Any],
) -> None:
    agents = config_data.get("agents")
    if not isinstance(agents, dict):
        agents = {}
        config_data["agents"] = agents
    defaults = agents.get("defaults")
    if not isinstance(defaults, dict):
        defaults = {}
        agents["defaults"] = defaults

    models = config_data.get("models")
    if not isinstance(models, dict):
        models = {}
        config_data["models"] = models

    default_model = _as_text(state.get("defaultModel"))
    fallback_models = _normalize_string_list(state.get("fallbackModels"))
    model_registry = _ensure_registry_contains_models(
        _normalize_string_list(state.get("modelRegistry")),
        [default_model, *fallback_models],
    )
    provider_configs = _normalize_provider_configs(state.get("providerConfigs"))

    defaults["model"] = default_model
    defaults["fallbackModels"] = fallback_models
    models["registry"] = model_registry
    models["providers"] = provider_configs

    write_config_file(config_path, config_data)


def _build_models_providers_payload(container) -> dict[str, Any]:
    _, _, state = _load_models_provider_state(container)
    _apply_models_provider_runtime(container, state)
    provider_configs = _normalize_provider_configs(state.get("providerConfigs"))
    providers = [
        _provider_entry_for_response(provider_id, entry)
        for provider_id, entry in sorted(provider_configs.items(), key=lambda item: item[0])
    ]
    catalog = {
        "providers": [_catalog_entry_for_provider(provider_id) for provider_id in _BUILTIN_PROVIDER_IDS],
        "customApis": sorted(_ALLOWED_CUSTOM_PROVIDER_APIS),
    }
    return {
        "catalog": catalog,
        "providers": providers,
        "defaults": {
            "defaultModel": _as_text(state.get("defaultModel")),
            "fallbackModels": _normalize_string_list(state.get("fallbackModels")),
        },
        "modelRegistry": _normalize_string_list(state.get("modelRegistry")),
    }


def _build_tools_catalog(websocket: WebSocket) -> dict[str, object]:
    tools = websocket.app.state.container.tool_registry.list()
    return {
        "profiles": [
            {"id": "minimal", "label": "Minimal"},
            {"id": "coding", "label": "Coding"},
            {"id": "messaging", "label": "Messaging"},
            {"id": "full", "label": "Full"},
        ],
        "groups": [
            {
                "id": "core",
                "label": "Tools",
                "source": "core",
                "tools": [
                    {
                        "id": tool.name,
                        "label": tool.name,
                        "description": tool.description,
                        "source": "core",
                        "optional": False,
                        "defaultProfiles": [],
                    }
                    for tool in tools
                ],
            }
        ],
    }


def _build_skills_status(websocket: WebSocket) -> dict[str, object]:
    from ...agents.skills.skills_status import compute_missing_bins, compute_missing_env

    container = websocket.app.state.container
    # Per-skill enabled state: dict[skillKey, bool]. Absence means enabled (default).
    skill_entries: dict[str, dict[str, object]] = _get_skill_entries_store(websocket)
    skills = []
    for skill in container.skill_catalog.list():
        entry_cfg = skill_entries.get(skill.key, {})
        # disabled only if explicitly set to False; absent or True = eligible
        is_eligible = entry_cfg.get("enabled", True) is not False

        # Compute missing bins and env for eligibility/status display
        missing_bins = compute_missing_bins(skill.required_bins)
        missing_env = compute_missing_env(skill.required_env)
        # Check if env is satisfied by skill entry apiKey config
        api_key_set = bool(entry_cfg.get("apiKey"))
        if api_key_set and skill.primary_env and skill.primary_env in missing_env:
            missing_env = [e for e in missing_env if e != skill.primary_env]

        has_missing = bool(missing_bins) or bool(missing_env)
        eligible = is_eligible and not has_missing
        # Check OS eligibility
        missing_os: list[str] = []
        if skill.required_os:
            import sys
            current_platform = sys.platform
            if current_platform not in skill.required_os:
                missing_os = [current_platform]
                eligible = False

        # Build install options list for the UI
        install_options: list[dict[str, object]] = []
        if skill.install and missing_bins:
            for opt in skill.install:
                install_options.append({
                    "id": opt.id,
                    "kind": opt.kind,
                    "label": opt.label,
                    "bins": opt.bins,
                })

        skills.append(
            {
                "name": skill.name,
                "description": skill.description,
                "source": skill.source or "local",
                "filePath": skill.file_path,
                "baseDir": "skills",
                "skillKey": skill.key,
                "bundled": skill.bundled,
                "primaryEnv": skill.primary_env or None,
                "emoji": skill.emoji or None,
                "homepage": skill.homepage or None,
                "always": False,
                "disabled": not is_eligible,
                "blockedByAllowlist": False,
                "eligible": eligible,
                "requirements": {
                    "bins": skill.required_bins,
                    "env": skill.required_env,
                    "config": skill.required_config,
                    "os": skill.required_os,
                },
                "missing": {
                    "bins": missing_bins,
                    "env": missing_env,
                    "config": [],
                    "os": missing_os,
                },
                "configChecks": [],
                "install": install_options,
            }
        )
    return {
        "workspaceDir": container.settings.workspace_dir,
        "managedSkillsDir": "skills",
        "skills": skills,
    }


def _build_config_snapshot(websocket: WebSocket) -> dict[str, object]:
    config = _get_control_ui_config_store(websocket)
    raw = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
    return {
        "path": "runtime://config",
        "exists": True,
        "raw": raw,
        "hash": _hash_json_payload(config),
        "parsed": config,
        "valid": True,
        "config": config,
        "issues": [],
    }


def _build_exec_approvals_snapshot(
    websocket: WebSocket,
    *,
    target_key: str,
) -> dict[str, object]:
    store = _get_exec_approvals_store(websocket)
    file = store.get(target_key)
    if not isinstance(file, dict):
        file = {"version": 1}
        store[target_key] = file
    return {
        "path": f"runtime://exec-approvals/{target_key}",
        "exists": True,
        "hash": _hash_json_payload(file),
        "file": file,
    }


@dataclass
class _ConnectionState:
    conn_id: str
    authenticated: bool
    auth: AuthContext | None
    role: str = "operator"
    scopes: list[str] = field(default_factory=list)
    started_at_ms: int = field(default_factory=_now_ms)


@dataclass
class _ActiveRun:
    run_id: str
    session_key: str
    task: asyncio.Task[None]


async def _start_chat_run(
    websocket: WebSocket,
    send_lock: asyncio.Lock,
    active_runs: dict[str, _ActiveRun],
    *,
    session_key: str,
    run_id: str,
    message: str,
    model: str | None,
    idempotency_key: str | None,
) -> None:
    container = websocket.app.state.container
    container.session_runtime.start_run(
        run_id=run_id,
        session_id=session_key,
        idempotency_key=idempotency_key,
    )

    async def _runner() -> None:
        aggregate = ""
        try:
            lock = container.session_runtime.lock_for_session(session_key)
            async with lock:
                session_messages = await _load_graph_session_messages(container, session_key)
                stream = await container.agent_runner.stream(
                    run_id=run_id,
                    session_id=session_key,
                    message=message,
                    model=model,
                    session_messages=session_messages,
                )
                async for token in stream:
                    aggregate += token
                    sent = await _send_frame(
                        websocket,
                        send_lock,
                        {
                            "type": "event",
                            "event": "chat",
                            "payload": {
                                "runId": run_id,
                                "sessionKey": session_key,
                                "state": "delta",
                                "message": {"role": "assistant", "text": aggregate},
                            },
                        },
                    )
                    if not sent:
                        return
            container.session_runtime.finish_run(run_id, status="completed")
            await _send_frame(
                websocket,
                send_lock,
                {
                    "type": "event",
                    "event": "chat",
                    "payload": {
                        "runId": run_id,
                        "sessionKey": session_key,
                        "state": "final",
                        "message": _build_assistant_message(aggregate),
                    },
                },
            )
        except asyncio.CancelledError:
            container.session_runtime.finish_run(run_id, status="aborted")
            payload: dict[str, object] = {
                "runId": run_id,
                "sessionKey": session_key,
                "state": "aborted",
            }
            if aggregate.strip():
                payload["message"] = _build_assistant_message(aggregate)
            await _send_frame(
                websocket,
                send_lock,
                {"type": "event", "event": "chat", "payload": payload},
            )
            raise
        except Exception as err:
            container.session_runtime.finish_run(run_id, status="failed")
            await _send_frame(
                websocket,
                send_lock,
                {
                    "type": "event",
                    "event": "chat",
                    "payload": {
                        "runId": run_id,
                        "sessionKey": session_key,
                        "state": "error",
                        "errorMessage": str(err),
                    },
                },
            )
        finally:
            container.tool_runtime.reset_run_state(run_id)
            active_runs.pop(run_id, None)

    task = asyncio.create_task(_runner())
    active_runs[run_id] = _ActiveRun(run_id=run_id, session_key=session_key, task=task)


def _reset_session_for_key(
    *,
    container,
    session_meta: dict[str, dict[str, object]],
    active_runs: dict[str, _ActiveRun],
    key: str,
    now: int,
) -> bool:
    reset = False
    repo = container.session_repo
    if hasattr(repo, "_messages") and isinstance(repo._messages, dict):  # type: ignore[attr-defined]
        repo._messages[key] = []  # type: ignore[attr-defined]
        reset = True

    meta = dict(session_meta.get(key, {}))
    meta["updatedAt"] = now
    session_meta[key] = meta

    for run in [entry for entry in active_runs.values() if entry.session_key == key]:
        run.task.cancel()
        container.session_runtime.abort_run(run.run_id)

    return reset


async def _handle_connect(
    websocket: WebSocket,
    state: _ConnectionState,
    settings,
    params: dict[str, object],
) -> tuple[bool, object]:
    if not state.authenticated:
        auth_payload = params.get("auth")
        token = ""
        if isinstance(auth_payload, dict):
            token = _as_text(auth_payload.get("token"))
        if not token:
            if getattr(settings, "env", "") == "dev":
                state.auth = AuthContext(
                    subject="operator",
                    scopes=("operator.admin", "operator.write", "operator.read"),
                )
                state.authenticated = True
            else:
                return (
                    False,
                    _res_error(
                        "",
                        "UNAUTHORIZED",
                        "missing auth token",
                        details={"code": "AUTH_TOKEN_MISSING"},
                    )["error"],
                )
        if token:
            try:
                state.auth = _decode_token(token, settings)
                state.authenticated = True
            except HTTPException:
                return (
                    False,
                    _res_error(
                        "",
                        "UNAUTHORIZED",
                        "unauthorized",
                        details={"code": "AUTH_TOKEN_MISMATCH"},
                    )["error"],
                )

    state.role = _as_text(params.get("role"), "operator") or "operator"
    fallback_scopes = list(state.auth.scopes) if state.auth is not None else ["operator.admin"]
    state.scopes = _as_scope_list(params.get("scopes"), fallback_scopes)

    health = await _build_health_summary(websocket)
    payload = {
        "type": "hello-ok",
        "protocol": 3,
        "server": {
            "version": get_version(),
            "connId": state.conn_id,
        },
        "features": {
            "methods": SUPPORTED_METHODS,
            "events": ["chat", "presence", "exec.approval.requested", "exec.approval.resolved"],
        },
        "snapshot": {
            "presence": [],
            "health": health,
            "sessionDefaults": {
                "defaultAgentId": "main",
                "mainKey": "main",
                "mainSessionKey": "main",
                "scope": "agent",
            },
            "updateAvailable": None,
        },
        "auth": {
            "role": state.role,
            "scopes": state.scopes,
            "issuedAtMs": _now_ms(),
        },
        "policy": {"tickIntervalMs": 10_000},
    }
    return True, payload


async def _dispatch_method(
    websocket: WebSocket,
    send_lock: asyncio.Lock,
    active_runs: dict[str, _ActiveRun],
    state: _ConnectionState,
    method: str,
    params: dict[str, object],
) -> tuple[bool, object]:
    container = websocket.app.state.container
    session_meta = _get_session_meta_store(websocket)
    now = _now_ms()

    if method == "status":
        return True, await _build_status_summary(websocket, state.conn_id)

    if method == "health":
        return True, await _build_health_summary(websocket)

    if method == "last-heartbeat":
        started_at_ms = _as_int(getattr(websocket.app.state, "gateway_started_at_ms", None))
        if started_at_ms is None:
            started_at_ms = now
            websocket.app.state.gateway_started_at_ms = started_at_ms
        return True, {"ts": now, "uptimeMs": max(0, now - started_at_ms)}

    if method == "models.list":
        return True, {"models": _build_model_catalog(container)}

    if method == "models.providers.get":
        return True, _build_models_providers_payload(container)

    if method == "models.providers.apply":
        defaults_patch = params.get("defaults")
        registry_patch = params.get("modelRegistry")
        providers_patch = params.get("providers")

        config_path, config_data, state = _load_models_provider_state(container)

        if defaults_patch is not None:
            if not isinstance(defaults_patch, dict):
                return False, {"code": "INVALID_REQUEST", "message": "defaults must be an object"}
            if "defaultModel" in defaults_patch or "default" in defaults_patch:
                next_default_model = _as_text(
                    defaults_patch.get("defaultModel", defaults_patch.get("default"))
                )
                if next_default_model:
                    state["defaultModel"] = next_default_model
            if "fallbackModels" in defaults_patch or "fallback" in defaults_patch:
                state["fallbackModels"] = _normalize_string_list(
                    defaults_patch.get("fallbackModels", defaults_patch.get("fallback"))
                )

        if registry_patch is not None:
            if not isinstance(registry_patch, list):
                return False, {
                    "code": "INVALID_REQUEST",
                    "message": "modelRegistry must be an array",
                }
            state["modelRegistry"] = _normalize_string_list(registry_patch)

        current_provider_configs = _normalize_provider_configs(state.get("providerConfigs"))
        try:
            merged_provider_configs = _merge_provider_configs(
                current_provider_configs,
                providers_patch,
            )
        except ValueError as err:
            return False, {"code": "INVALID_REQUEST", "message": str(err)}
        state["providerConfigs"] = merged_provider_configs

        _persist_models_provider_state(
            config_path=config_path,
            config_data=config_data,
            state=state,
        )
        _apply_models_provider_runtime(container, state)
        return True, {"ok": True, "appliedAt": _utc_iso_now()}

    if method == "models.providers.delete":
        provider_id = _as_text(params.get("providerId")).lower()
        if not provider_id:
            return False, {"code": "INVALID_REQUEST", "message": "providerId is required"}

        config_path, config_data, state = _load_models_provider_state(container)
        provider_configs = _normalize_provider_configs(state.get("providerConfigs"))
        canonical_id = canonical_provider_id(provider_id)
        provider_configs.pop(canonical_id, None)
        state["providerConfigs"] = provider_configs

        _persist_models_provider_state(
            config_path=config_path,
            config_data=config_data,
            state=state,
        )
        _apply_models_provider_runtime(container, state)
        return True, {"ok": True}

    if method == "chat.history":
        session_key = _as_text(params.get("sessionKey"), "main") or "main"
        limit = _as_int(params.get("limit")) or 0
        messages = await container.session_repo.list_messages(session_key)
        if limit > 0:
            messages = messages[-limit:]
        payload_messages = [
            {
                "id": msg.id,
                "role": msg.role,
                "text": msg.text,
                "content": [{"type": "text", "text": msg.text}],
                "timestamp": msg.created_at_ms,
            }
            for msg in messages
        ]
        return True, {
            "messages": payload_messages,
            "thinkingLevel": _as_text(session_meta.get(session_key, {}).get("thinkingLevel"))
            or None,
        }

    if method == "chat.send":
        session_key = _as_text(params.get("sessionKey"), "main") or "main"
        message = _as_text(params.get("message"))
        attachments = params.get("attachments")
        has_attachments = isinstance(attachments, list) and len(attachments) > 0
        if not message and not has_attachments:
            return False, {
                "code": "INVALID_REQUEST",
                "message": "message is required",
            }
        if not message and has_attachments:
            message = "[Attachment]"

        idempotency_key = _as_text(params.get("idempotencyKey")) or None
        run_id = idempotency_key or f"run_{uuid.uuid4().hex}"

        if run_id in active_runs:
            return True, {"accepted": True, "runId": run_id, "deduplicated": True}

        existing_run = container.session_runtime.find_run_by_idempotency(
            session_id=session_key,
            idempotency_key=idempotency_key,
        )
        if existing_run:
            await _send_frame(
                websocket,
                send_lock,
                {
                    "type": "event",
                    "event": "chat",
                    "payload": {
                        "runId": existing_run,
                        "sessionKey": session_key,
                        "state": "final",
                        "message": _build_assistant_message(
                            "(deduplicated request, no re-execution)"
                        ),
                    },
                },
            )
            return True, {"accepted": True, "runId": existing_run, "deduplicated": True}

        command_message = message.lower()
        if command_message in {"/new", "/reset"}:
            reset = _reset_session_for_key(
                container=container,
                session_meta=session_meta,
                active_runs=active_runs,
                key=session_key,
                now=now,
            )
            await _send_frame(
                websocket,
                send_lock,
                {
                    "type": "event",
                    "event": "chat",
                    "payload": {
                        "runId": run_id,
                        "sessionKey": session_key,
                        "state": "final",
                    },
                },
            )
            return True, {
                "accepted": True,
                "runId": run_id,
                "reset": reset,
                "reason": "new" if command_message == "/new" else "reset",
            }

        requested_model = params.get("model")
        model = None
        try:
            model = _validate_requested_model(container, requested_model)
        except ValueError as exc:
            return False, {"code": "INVALID_REQUEST", "message": str(exc)}

        if model is None:
            model = _as_text(session_meta.get(session_key, {}).get("model")) or None
        if model:
            provider, _ = _split_model_key(model)
            meta = dict(session_meta.get(session_key, {}))
            meta["model"] = model
            meta["modelProvider"] = provider
            meta["updatedAt"] = now
            session_meta[session_key] = meta

        await _start_chat_run(
            websocket,
            send_lock,
            active_runs,
            session_key=session_key,
            run_id=run_id,
            message=message,
            model=model,
            idempotency_key=idempotency_key,
        )
        return True, {"accepted": True, "runId": run_id}

    if method == "chat.abort":
        run_id = _as_text(params.get("runId"))
        session_key = _as_text(params.get("sessionKey"))
        targets: list[_ActiveRun] = []
        if run_id:
            entry = active_runs.get(run_id)
            if entry is not None:
                targets.append(entry)
        elif session_key:
            targets.extend([entry for entry in active_runs.values() if entry.session_key == session_key])

        for target in targets:
            container.session_runtime.abort_run(target.run_id)
            target.task.cancel()

        return True, {"aborted": len(targets) > 0, "count": len(targets)}

    if method == "sessions.list":
        active_minutes = max(0, _as_int(params.get("activeMinutes")) or 0)
        limit = max(0, _as_int(params.get("limit")) or 0)
        rows, total = await _collect_session_rows(
            websocket, active_minutes=active_minutes, limit=limit
        )
        return True, {
            "ts": now,
            "path": "memory://sessions",
            "count": total,
            "defaults": {
                "model": str(container.runtime_config.get("defaultModel", "")).strip() or None,
                "contextTokens": None,
            },
            "sessions": rows,
        }

    if method == "sessions.patch":
        key = _as_text(params.get("key"))
        if not key:
            return False, {"code": "INVALID_REQUEST", "message": "missing session key"}
        patchable_keys = [
            "label",
            "thinkingLevel",
            "fastMode",
            "verboseLevel",
            "reasoningLevel",
            "model",
            "modelProvider",
            "contextTokens",
            "elevatedLevel",
        ]
        next_meta = dict(session_meta.get(key, {}))
        for field_name in patchable_keys:
            if field_name not in params:
                continue
            value = params.get(field_name)
            if value is None:
                next_meta.pop(field_name, None)
            else:
                next_meta[field_name] = value
        model = _as_text(next_meta.get("model"))
        if model and not _as_text(next_meta.get("modelProvider")):
            provider, _ = _split_model_key(model)
            next_meta["modelProvider"] = provider
        next_meta["updatedAt"] = now
        session_meta[key] = next_meta
        return True, {
            "ok": True,
            "path": "memory://sessions",
            "key": key,
            "entry": {"sessionId": key, "updatedAt": now, **next_meta},
        }

    if method == "sessions.delete":
        key = _as_text(params.get("key"))
        if not key:
            return False, {"code": "INVALID_REQUEST", "message": "missing session key"}
        deleted = False
        if key in session_meta:
            session_meta.pop(key, None)
            deleted = True
        repo = container.session_repo
        if hasattr(repo, "_sessions") and isinstance(repo._sessions, dict):  # type: ignore[attr-defined]
            if key in repo._sessions:  # type: ignore[attr-defined]
                repo._sessions.pop(key, None)  # type: ignore[attr-defined]
                deleted = True
        if hasattr(repo, "_messages") and isinstance(repo._messages, dict):  # type: ignore[attr-defined]
            if key in repo._messages:  # type: ignore[attr-defined]
                repo._messages.pop(key, None)  # type: ignore[attr-defined]
                deleted = True
        for run in [entry for entry in active_runs.values() if entry.session_key == key]:
            run.task.cancel()
            container.session_runtime.abort_run(run.run_id)
        return True, {"ok": True, "path": "memory://sessions", "key": key, "deleted": deleted}

    if method == "sessions.reset":
        key = _as_text(params.get("key"))
        if not key:
            return False, {"code": "INVALID_REQUEST", "message": "missing session key"}
        reset = _reset_session_for_key(
            container=container,
            session_meta=session_meta,
            active_runs=active_runs,
            key=key,
            now=now,
        )
        return True, {"ok": True, "path": "memory://sessions", "key": key, "reset": reset}

    if method == "sessions.compact":
        key = _as_text(params.get("key"))
        return True, {"ok": True, "key": key or "main"}

    if method == "system-presence":
        return True, []

    if method == "agents.list":
        return True, {
            "defaultId": "main",
            "mainKey": "main",
            "scope": "agent",
            "agents": [
                {
                    "id": "main",
                    "name": "Assistant",
                    "identity": {"name": "Assistant", "avatar": "A", "emoji": "A"},
                }
            ],
        }

    if method == "agent.identity.get":
        agent_id = _as_text(params.get("agentId"))
        if not agent_id:
            session_key = _as_text(params.get("sessionKey"), "main") or "main"
            agent_id = _parse_agent_id_from_session_key(session_key)
        return True, {
            "agentId": agent_id,
            "name": "Assistant",
            "avatar": "A",
            "emoji": "A",
        }

    if method == "agents.files.list":
        agent_id = _as_text(params.get("agentId"), "main") or "main"
        file_store = _get_agent_files_store(websocket).get(agent_id, {})
        files = [
            {
                "name": name,
                "path": name,
                "missing": False,
                "size": len(content.encode("utf-8")),
                "updatedAtMs": now,
            }
            for name, content in sorted(file_store.items())
        ]
        return True, {
            "agentId": agent_id,
            "workspace": container.settings.workspace_dir,
            "files": files,
        }

    if method == "agents.files.get":
        agent_id = _as_text(params.get("agentId"), "main") or "main"
        name = _as_text(params.get("name"))
        if not name:
            return False, {"code": "INVALID_REQUEST", "message": "missing file name"}
        file_store = _get_agent_files_store(websocket).setdefault(agent_id, {})
        content = file_store.get(name, "")
        return True, {
            "agentId": agent_id,
            "workspace": container.settings.workspace_dir,
            "file": {
                "name": name,
                "path": name,
                "missing": name not in file_store,
                "size": len(content.encode("utf-8")),
                "updatedAtMs": now,
                "content": content,
            },
        }

    if method == "agents.files.set":
        agent_id = _as_text(params.get("agentId"), "main") or "main"
        name = _as_text(params.get("name"))
        content = params.get("content")
        if not name or not isinstance(content, str):
            return False, {"code": "INVALID_REQUEST", "message": "name/content required"}
        file_store = _get_agent_files_store(websocket).setdefault(agent_id, {})
        file_store[name] = content
        return True, {
            "ok": True,
            "agentId": agent_id,
            "workspace": container.settings.workspace_dir,
            "file": {
                "name": name,
                "path": name,
                "missing": False,
                "size": len(content.encode("utf-8")),
                "updatedAtMs": now,
                "content": content,
            },
        }

    if method == "node.list":
        return True, {"nodes": []}

    if method == "device.pair.list":
        return True, {"pending": [], "paired": []}

    if method == "device.pair.approve":
        return True, {"ok": True}

    if method == "device.pair.reject":
        return True, {"ok": True}

    if method == "device.token.rotate":
        device_id = _as_text(params.get("deviceId"), "local-device") or "local-device"
        role = _as_text(params.get("role"), "operator") or "operator"
        token = f"device_{uuid.uuid4().hex}"
        return True, {"token": token, "deviceId": device_id, "role": role, "scopes": []}

    if method == "device.token.revoke":
        return True, {"ok": True}

    if method == "logs.tail":
        cursor = max(0, _as_int(params.get("cursor")) or 0)
        limit = max(1, min(1000, _as_int(params.get("limit")) or 100))
        logs = _get_log_buffer(websocket)
        lines = logs[cursor : cursor + limit]
        next_cursor = cursor + len(lines)
        return True, {
            "file": "python-gateway.log",
            "cursor": next_cursor,
            "size": len(logs),
            "lines": lines,
            "truncated": False,
            "reset": cursor == 0,
        }

    if method == "config.get":
        return True, _build_config_snapshot(websocket)

    if method == "config.schema":
        return True, {
            "schema": {"type": "object", "properties": {}},
            "uiHints": {},
            "version": "python-compat",
            "generatedAt": _utc_iso_now(),
        }

    if method in {"config.set", "config.apply"}:
        raw = params.get("raw")
        if not isinstance(raw, str):
            return False, {"code": "INVALID_REQUEST", "message": "raw must be string"}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as err:
            return False, {"code": "INVALID_REQUEST", "message": f"invalid JSON: {err.msg}"}
        if not isinstance(parsed, dict):
            return False, {"code": "INVALID_REQUEST", "message": "config root must be object"}
        websocket.app.state.control_ui_config_store = parsed
        return True, {"ok": True}

    if method == "config.openFile":
        return True, {"path": "runtime://config"}

    if method == "channels.status":
        return True, {
            "ts": now,
            "channelOrder": [],
            "channelLabels": {},
            "channelDetailLabels": {},
            "channelSystemImages": {},
            "channels": {},
            "channelAccounts": {},
            "channelDefaultAccountId": {},
        }

    if method == "channels.logout":
        return True, {"ok": True}

    if method == "web.login.start":
        return True, {"message": "Web login is not enabled in this Python backend", "qrDataUrl": None}

    if method == "web.login.wait":
        return True, {"message": "Web login is not enabled in this Python backend", "connected": False}

    if method == "skills.status":
        return True, _build_skills_status(websocket)

    if method == "skills.update":
        skill_key = _as_text(params.get("skillKey"))
        if not skill_key:
            return True, {"ok": False, "error": "skillKey is required"}

        enabled = params.get("enabled")
        api_key_param = params.get("apiKey")
        # Per-skill state store: dict[skillKey -> {"enabled": bool, "apiKey": str, ...}]
        skill_entries = _get_skill_entries_store(websocket)
        current = dict(skill_entries.get(skill_key, {}))
        if isinstance(enabled, bool):
            current["enabled"] = enabled
        if isinstance(api_key_param, str):
            api_key_val = api_key_param.strip()
            if api_key_val:
                current["apiKey"] = api_key_val
            else:
                current.pop("apiKey", None)

            # Persist apiKey into the config file under skills.entries.<skillKey>.apiKey
            # Mirrors openclaw's skills.entries[skillKey] config structure.
            try:
                config_path = resolve_config_path()
                config_data: dict[str, Any] = {}
                try:
                    loaded = read_config_file(config_path)
                    if isinstance(loaded, dict):
                        config_data = loaded
                except FileNotFoundError:
                    pass
                skills_section = config_data.setdefault("skills", {})
                entries_section = skills_section.setdefault("entries", {})
                entry = entries_section.setdefault(skill_key, {})
                if api_key_val:
                    entry["apiKey"] = api_key_val
                else:
                    entry.pop("apiKey", None)
                    if not entry:
                        entries_section.pop(skill_key, None)
                write_config_file(config_path, config_data)
            except Exception:
                pass

            # Also set the env var for immediate availability
            container = websocket.app.state.container
            # Find the primaryEnv for this skill to set as env var
            for skill in container.skill_catalog.list():
                if skill.key == skill_key and skill.primary_env:
                    import os as _os
                    if api_key_val:
                        _os.environ[skill.primary_env] = api_key_val
                    else:
                        _os.environ.pop(skill.primary_env, None)
                    break

        skill_entries[skill_key] = current

        # Build a disabled-set for the agent runner from all per-skill entries.
        # Skills absent from the store are considered enabled (default).
        disabled_keys = {k for k, v in skill_entries.items() if v.get("enabled") is False}
        container = websocket.app.state.container
        # Pass None = all enabled; pass a tuple of ENABLED keys when some are disabled.
        all_keys = {s.key for s in container.skill_catalog.list()}
        if disabled_keys:
            allowed = tuple(k for k in all_keys if k not in disabled_keys)
            container.agent_runner.update_skills_enabled(allowed)
            container.runtime_config["skillsEnabled"] = allowed
        else:
            # No disabled skills → no filter
            container.agent_runner.update_skills_enabled(None)
            container.runtime_config["skillsEnabled"] = None

        _append_gateway_log(
            websocket,
            f"skills.update: {skill_key} enabled={enabled}, disabled_keys={disabled_keys or '(none)'}",
        )
        return True, {"ok": True, "skillKey": skill_key, "config": current}

    if method == "skills.install":
        container = websocket.app.state.container
        # Reload skill catalog to pick up any new skills
        container.skill_catalog.reload()
        _append_gateway_log(websocket, "skills.install: reloaded skill catalog")
        return True, _build_skills_status(websocket)

    if method == "tools.catalog":
        return True, _build_tools_catalog(websocket)

    if method == "cron.status":
        return True, {"enabled": False, "jobs": 0, "nextWakeAtMs": None}

    if method == "cron.list":
        limit = max(1, _as_int(params.get("limit")) or 50)
        offset = max(0, _as_int(params.get("offset")) or 0)
        return True, {
            "jobs": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "nextOffset": None,
            "hasMore": False,
        }

    if method == "cron.runs":
        limit = max(1, _as_int(params.get("limit")) or 50)
        offset = max(0, _as_int(params.get("offset")) or 0)
        return True, {
            "entries": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "nextOffset": None,
            "hasMore": False,
        }

    if method in {"cron.add", "cron.update", "cron.remove", "cron.run"}:
        return True, {"ok": True}

    if method == "exec.approvals.get":
        return True, _build_exec_approvals_snapshot(websocket, target_key="gateway")

    if method == "exec.approvals.node.get":
        node_id = _as_text(params.get("nodeId"), "node") or "node"
        return True, _build_exec_approvals_snapshot(websocket, target_key=f"node:{node_id}")

    if method in {"exec.approvals.set", "exec.approvals.node.set"}:
        target_key = "gateway"
        if method == "exec.approvals.node.set":
            node_id = _as_text(params.get("nodeId"), "node") or "node"
            target_key = f"node:{node_id}"
        file = params.get("file")
        if not isinstance(file, dict):
            return False, {"code": "INVALID_REQUEST", "message": "file must be object"}
        store = _get_exec_approvals_store(websocket)
        store[target_key] = file
        return True, {"ok": True}

    if method == "exec.approval.resolve":
        return True, {"ok": True}

    if method == "sessions.usage":
        return True, {
            "updatedAt": now,
            "startDate": _as_text(params.get("startDate")),
            "endDate": _as_text(params.get("endDate")),
            "sessions": [],
            "totals": _empty_usage_totals(),
            "aggregates": _empty_usage_aggregates(),
        }

    if method == "usage.cost":
        return True, {
            "updatedAt": now,
            "days": 0,
            "daily": [],
            "totals": _empty_usage_totals(),
        }

    if method == "sessions.usage.timeseries":
        key = _as_text(params.get("key"))
        return True, {"sessionId": key or None, "points": []}

    if method == "sessions.usage.logs":
        return True, {"logs": []}

    if method == "update.run":
        return True, {
            "ok": True,
            "result": {
                "status": "skipped",
                "reason": "update pipeline not configured in python backend",
            },
        }

    return False, {"code": "NOT_FOUND", "message": f"method not found: {method}"}


@router.websocket("/v1/ws/chat")
async def chat_socket(websocket: WebSocket) -> None:
    settings = load_settings()
    pre_auth: AuthContext | None = None
    try:
        pre_auth = resolve_websocket_auth(websocket, settings)
    except HTTPException:
        pre_auth = None

    await websocket.accept()
    _append_gateway_log(websocket, "websocket client connected")

    conn_state = _ConnectionState(
        conn_id=f"conn_{uuid.uuid4().hex[:12]}",
        authenticated=pre_auth is not None,
        auth=pre_auth,
        scopes=list(pre_auth.scopes) if pre_auth is not None else [],
    )
    send_lock = asyncio.Lock()
    active_runs: dict[str, _ActiveRun] = {}

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                frame = json.loads(raw)
            except json.JSONDecodeError:
                await _send_frame(
                    websocket,
                    send_lock,
                    _res_error("", "INVALID_REQUEST", "invalid JSON"),
                )
                continue

            if not isinstance(frame, dict):
                await _send_frame(
                    websocket,
                    send_lock,
                    _res_error("", "INVALID_REQUEST", "frame must be a JSON object"),
                )
                continue

            frame_type = _as_text(frame.get("type"))
            if frame_type == "ping":
                await _send_frame(websocket, send_lock, {"type": "pong"})
                continue

            if frame_type != "req":
                await _send_frame(
                    websocket,
                    send_lock,
                    _res_error("", "INVALID_REQUEST", f"unsupported frame type: {frame_type or 'unknown'}"),
                )
                continue

            req_id = _as_text(frame.get("id"))
            method = _as_text(frame.get("method"))
            if not method:
                await _send_frame(
                    websocket,
                    send_lock,
                    _res_error(req_id, "INVALID_REQUEST", "missing method"),
                )
                continue

            raw_params = frame.get("params")
            params = raw_params if isinstance(raw_params, dict) else {}

            if method == "connect":
                ok, payload = await _handle_connect(websocket, conn_state, settings, params)
                if ok:
                    await _send_frame(websocket, send_lock, _res_ok(req_id, payload))
                else:
                    error = payload if isinstance(payload, dict) else {}
                    await _send_frame(
                        websocket,
                        send_lock,
                        _res_error(
                            req_id,
                            _as_text(error.get("code"), "UNAUTHORIZED"),
                            _as_text(error.get("message"), "unauthorized"),
                            details=error.get("details"),
                        ),
                    )
                continue

            if not conn_state.authenticated:
                await _send_frame(
                    websocket,
                    send_lock,
                    _res_error(
                        req_id,
                        "UNAUTHORIZED",
                        "connect required",
                        details={"code": "AUTH_REQUIRED"},
                    ),
                )
                continue

            try:
                ok, payload = await _dispatch_method(
                    websocket,
                    send_lock,
                    active_runs,
                    conn_state,
                    method,
                    params,
                )
            except Exception as err:
                _append_gateway_log(websocket, f"method {method} failed: {err}", level="error")
                await _send_frame(
                    websocket,
                    send_lock,
                    _res_error(req_id, "INTERNAL_ERROR", str(err)),
                )
                continue

            if ok:
                await _send_frame(websocket, send_lock, _res_ok(req_id, payload))
            else:
                error = payload if isinstance(payload, dict) else {}
                await _send_frame(
                    websocket,
                    send_lock,
                    _res_error(
                        req_id,
                        _as_text(error.get("code"), "INVALID_REQUEST"),
                        _as_text(error.get("message"), "request failed"),
                        details=error.get("details"),
                    ),
                )
    except WebSocketDisconnect:
        pass
    finally:
        _append_gateway_log(websocket, "websocket client disconnected")
        running = list(active_runs.values())
        for run in running:
            run.task.cancel()
        if running:
            await asyncio.gather(*(run.task for run in running), return_exceptions=True)
