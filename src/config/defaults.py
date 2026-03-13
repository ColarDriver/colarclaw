"""Configuration defaults application.

Ported from bk/src/config/defaults.ts (537 lines), agent-limits.ts,
model-input.ts, talk.ts, talk-defaults.ts, port-defaults.ts.

Applies sensible defaults to loaded config: models, agents, sessions,
logging, messages, compaction, context pruning, and talk/TTS.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ─── Constants ───

DEFAULT_CONTEXT_TOKENS = 200_000
DEFAULT_MODEL_MAX_TOKENS = 8192
DEFAULT_AGENT_MAX_CONCURRENT = 5
DEFAULT_SUBAGENT_MAX_CONCURRENT = 3
DEFAULT_MODEL_INPUT = ["text"]
DEFAULT_TALK_PROVIDER = "elevenlabs"

DEFAULT_MODEL_ALIASES: dict[str, str] = {
    "opus": "anthropic/claude-opus-4-6",
    "sonnet": "anthropic/claude-sonnet-4-6",
    "gpt": "openai/gpt-5.4",
    "gpt-mini": "openai/gpt-5-mini",
    "gemini": "google/gemini-3.1-pro-preview",
    "gemini-flash": "google/gemini-3-flash-preview",
    "gemini-flash-lite": "google/gemini-3.1-flash-lite-preview",
}


def _is_positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and value > 0


# ─── Message defaults ───

def apply_message_defaults(cfg: dict[str, Any]) -> dict[str, Any]:
    """Apply message defaults (ackReactionScope)."""
    messages = cfg.get("messages", {}) or {}
    if "ackReactionScope" in messages:
        return cfg
    return {
        **cfg,
        "messages": {**messages, "ackReactionScope": "group-mentions"},
    }


# ─── Session defaults ───

_session_warned = False


def apply_session_defaults(cfg: dict[str, Any]) -> dict[str, Any]:
    """Apply session defaults (mainKey always 'main')."""
    global _session_warned
    session = cfg.get("session")
    if not session or session.get("mainKey") is None:
        return cfg
    trimmed = str(session.get("mainKey", "")).strip()
    result = {**cfg, "session": {**session, "mainKey": "main"}}
    if trimmed and trimmed != "main" and not _session_warned:
        _session_warned = True
        logger.warning('session.mainKey is ignored; main session is always "main".')
    return result


# ─── Logging defaults ───

def apply_logging_defaults(cfg: dict[str, Any]) -> dict[str, Any]:
    """Apply logging defaults (redactSensitive)."""
    log_cfg = cfg.get("logging")
    if not log_cfg:
        return cfg
    if log_cfg.get("redactSensitive"):
        return cfg
    return {**cfg, "logging": {**log_cfg, "redactSensitive": "tools"}}


# ─── Agent defaults ───

def apply_agent_defaults(cfg: dict[str, Any]) -> dict[str, Any]:
    """Apply agent defaults (maxConcurrent, subagents.maxConcurrent)."""
    agents = cfg.get("agents", {}) or {}
    defaults = agents.get("defaults", {}) or {}
    has_max = isinstance(defaults.get("maxConcurrent"), (int, float))
    subagents = defaults.get("subagents", {}) or {}
    has_sub_max = isinstance(subagents.get("maxConcurrent"), (int, float))
    if has_max and has_sub_max:
        return cfg

    mutated = False
    next_defaults = dict(defaults)
    if not has_max:
        next_defaults["maxConcurrent"] = DEFAULT_AGENT_MAX_CONCURRENT
        mutated = True
    next_subagents = dict(subagents)
    if not has_sub_max:
        next_subagents["maxConcurrent"] = DEFAULT_SUBAGENT_MAX_CONCURRENT
        mutated = True

    if not mutated:
        return cfg
    next_defaults["subagents"] = next_subagents
    return {**cfg, "agents": {**agents, "defaults": next_defaults}}


# ─── Model defaults ───

def _resolve_model_cost(raw: dict[str, Any] | None) -> dict[str, float]:
    """Resolve model cost with defaults."""
    r = raw or {}
    return {
        "input": r.get("input", 0),
        "output": r.get("output", 0),
        "cacheRead": r.get("cacheRead", 0),
        "cacheWrite": r.get("cacheWrite", 0),
    }


def _resolve_default_provider_api(
    provider_id: str,
    provider_api: str | None = None,
) -> str | None:
    if provider_api:
        return provider_api
    return "anthropic-messages" if provider_id.lower() == "anthropic" else None


def apply_model_defaults(cfg: dict[str, Any]) -> dict[str, Any]:
    """Apply model defaults: cost, context window, max tokens, API format."""
    models_cfg = cfg.get("models", {}) or {}
    provider_config = models_cfg.get("providers")
    if not provider_config:
        return cfg

    mutated = False
    next_providers = dict(provider_config)

    for provider_id, provider in provider_config.items():
        if not isinstance(provider, dict):
            continue
        models = provider.get("models", [])
        if not isinstance(models, list) or not models:
            continue

        provider_api = _resolve_default_provider_api(
            provider_id, provider.get("api"),
        )
        next_provider = dict(provider)
        if provider_api and provider.get("api") != provider_api:
            next_provider["api"] = provider_api
            mutated = True

        provider_mutated = False
        next_models = []
        for model in models:
            if not isinstance(model, dict):
                next_models.append(model)
                continue

            m = dict(model)
            model_mutated = False

            # Reasoning
            if not isinstance(m.get("reasoning"), bool):
                m["reasoning"] = False
                model_mutated = True

            # Input
            if m.get("input") is None:
                m["input"] = list(DEFAULT_MODEL_INPUT)
                model_mutated = True

            # Cost
            old_cost = m.get("cost")
            m["cost"] = _resolve_model_cost(old_cost)
            if old_cost != m["cost"]:
                model_mutated = True

            # Context window
            ctx = m.get("contextWindow")
            if not _is_positive_number(ctx):
                m["contextWindow"] = DEFAULT_CONTEXT_TOKENS
                model_mutated = True

            # Max tokens
            ctx_win = m["contextWindow"]
            raw_max = m.get("maxTokens")
            if not _is_positive_number(raw_max):
                raw_max = min(DEFAULT_MODEL_MAX_TOKENS, ctx_win)
            m["maxTokens"] = min(raw_max, ctx_win)
            if m["maxTokens"] != model.get("maxTokens"):
                model_mutated = True

            # API
            if m.get("api") is None and provider_api:
                m["api"] = provider_api
                model_mutated = True

            if model_mutated:
                provider_mutated = True
            next_models.append(m if model_mutated else model)

        if provider_mutated:
            next_provider["models"] = next_models
            next_providers[provider_id] = next_provider
            mutated = True

    if not mutated:
        return cfg
    return {**cfg, "models": {**models_cfg, "providers": next_providers}}


# ─── Compaction defaults ───

def apply_compaction_defaults(cfg: dict[str, Any]) -> dict[str, Any]:
    """Apply compaction defaults (mode: 'safeguard')."""
    agents = cfg.get("agents", {}) or {}
    defaults = agents.get("defaults", {}) or {}
    if not defaults:
        return cfg
    compaction = defaults.get("compaction", {}) or {}
    if compaction.get("mode"):
        return cfg
    return {
        **cfg,
        "agents": {
            **agents,
            "defaults": {
                **defaults,
                "compaction": {**compaction, "mode": "safeguard"},
            },
        },
    }


# ─── Context pruning defaults ───

def _resolve_anthropic_auth_mode(cfg: dict[str, Any]) -> str | None:
    """Resolve default Anthropic auth mode from profiles."""
    auth = cfg.get("auth", {}) or {}
    profiles = auth.get("profiles", {}) or {}
    order = (auth.get("order", {}) or {}).get("anthropic", [])

    for profile_id in order:
        entry = profiles.get(profile_id)
        if not entry or entry.get("provider") != "anthropic":
            continue
        mode = entry.get("mode", "")
        if mode == "api_key":
            return "api_key"
        if mode in ("oauth", "token"):
            return "oauth"

    anthro_profiles = [
        p for p in profiles.values()
        if isinstance(p, dict) and p.get("provider") == "anthropic"
    ]
    has_api = any(p.get("mode") == "api_key" for p in anthro_profiles)
    has_oauth = any(p.get("mode") in ("oauth", "token") for p in anthro_profiles)

    if has_api and not has_oauth:
        return "api_key"
    if has_oauth and not has_api:
        return "oauth"

    if os.environ.get("ANTHROPIC_OAUTH_TOKEN", "").strip():
        return "oauth"
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return "api_key"
    return None


def apply_context_pruning_defaults(cfg: dict[str, Any]) -> dict[str, Any]:
    """Apply context pruning defaults based on Anthropic auth mode."""
    agents = cfg.get("agents", {}) or {}
    defaults = agents.get("defaults", {}) or {}
    if not defaults:
        return cfg

    auth_mode = _resolve_anthropic_auth_mode(cfg)
    if not auth_mode:
        return cfg

    mutated = False
    next_defaults = dict(defaults)

    ctx_pruning = defaults.get("contextPruning", {}) or {}
    if ctx_pruning.get("mode") is None:
        next_defaults["contextPruning"] = {
            **ctx_pruning,
            "mode": "cache-ttl",
            "ttl": ctx_pruning.get("ttl", "1h"),
        }
        mutated = True

    heartbeat = defaults.get("heartbeat", {}) or {}
    if heartbeat.get("every") is None:
        next_defaults["heartbeat"] = {
            **heartbeat,
            "every": "1h" if auth_mode == "oauth" else "30m",
        }
        mutated = True

    if not mutated:
        return cfg

    return {
        **cfg,
        "agents": {**agents, "defaults": next_defaults},
    }
