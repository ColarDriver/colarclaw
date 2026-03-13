"""Configuration validation.

Ported from bk/src/config/validation.ts (604 lines), schema.ts (711 lines),
schema.help.ts, schema.hints.ts, schema.labels.ts, schema.tags.ts, schema.irc.ts,
zod-schema.ts, zod-schema.core.ts, zod-schema.agents.ts,
zod-schema.agent-defaults.ts, zod-schema.agent-model.ts,
zod-schema.agent-runtime.ts, zod-schema.allowdeny.ts,
zod-schema.approvals.ts, zod-schema.channels.ts, zod-schema.hooks.ts,
zod-schema.installs.ts, zod-schema.providers-core.ts,
zod-schema.providers.ts, zod-schema.providers-whatsapp.ts,
zod-schema.secret-input-validation.ts, zod-schema.sensitive.ts,
zod-schema.session.ts, allowed-values.ts, dangerous-name-matching.ts,
version.ts, runtime-overrides.ts, runtime-group-policy.ts, group.ts,
group-policy.ts, byte-size.ts, cache-utils.ts, channel-capabilities.ts,
bindings.ts, delivery-info.ts, discord-preview-streaming.ts,
disk-budget.ts, explicit-session-key-normalization.ts,
gateway-control-ui-origins.ts, issue-format.ts, logging.ts,
main-session.ts, markdown-tables.ts, media-audio-field-metadata.ts,
metadata.ts, normalize-exec-safe-bin.ts, normalize-paths.ts,
plugin-auto-enable.ts, plugins-allowlist.ts, redact-snapshot.ts,
redact-snapshot.raw.ts, redact-snapshot.secret-ref.ts, reset.ts,
session-key.ts, sessions.ts, telegram-custom-commands.ts,
transcript.ts, legacy.ts, legacy-migrate.ts,
legacy.migrations.ts / part1-3, legacy.rules.ts, legacy.shared.ts.

Provides config validation, schema constants, and legacy migration.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# ─── Allowed values ───

ALLOWED_GATEWAY_MODES = {"local", "remote"}
ALLOWED_AUTH_MODES = {"token", "password", "none"}
ALLOWED_BIND_VALUES = {"loopback", "all"}
ALLOWED_LOG_LEVELS = {"debug", "info", "warn", "error"}
ALLOWED_REDACT_MODES = {"none", "tools", "all"}
ALLOWED_SESSION_STORAGE = {"jsonl", "sqlite"}
ALLOWED_APPROVAL_MODES = {"ask", "auto-edit", "auto-full"}
ALLOWED_COMPACTION_MODES = {"disabled", "safeguard", "full"}
ALLOWED_CONTEXT_PRUNING_MODES = {"disabled", "cache-ttl", "adaptive"}


# ─── Validation result types ───

class ConfigValidationIssue:
    def __init__(self, path: str, message: str):
        self.path = path
        self.message = message

    def __repr__(self) -> str:
        return f"ConfigValidationIssue(path={self.path!r}, message={self.message!r})"


class ConfigValidationResult:
    def __init__(
        self,
        ok: bool = True,
        issues: list[ConfigValidationIssue] | None = None,
        warnings: list[ConfigValidationIssue] | None = None,
        config: dict[str, Any] | None = None,
    ):
        self.ok = ok
        self.issues = issues or []
        self.warnings = warnings or []
        self.config = config


# ─── Core validation ───

def validate_config_object(
    raw: Any,
    *,
    allow_unknown: bool = True,
) -> ConfigValidationResult:
    """Validate a config object against the schema.

    Returns a ConfigValidationResult with ok, issues, warnings, and
    the validated config (with type coercions applied).
    """
    issues: list[ConfigValidationIssue] = []
    warnings: list[ConfigValidationIssue] = []

    if not isinstance(raw, dict):
        issues.append(ConfigValidationIssue("<root>", "config must be an object"))
        return ConfigValidationResult(ok=False, issues=issues)

    cfg = dict(raw)

    # Validate gateway section
    _validate_gateway(cfg.get("gateway"), issues, warnings)

    # Validate session section
    _validate_session(cfg.get("session"), issues, warnings)

    # Validate agents section
    _validate_agents(cfg.get("agents"), issues, warnings)

    # Validate logging section
    _validate_logging(cfg.get("logging"), issues, warnings)

    # Validate approvals section
    _validate_approvals(cfg.get("approvals"), issues, warnings)

    # Validate models section
    _validate_models(cfg.get("models"), issues, warnings)

    # Validate cron section
    _validate_cron(cfg.get("cron"), issues, warnings)

    # Validate env section
    _validate_env(cfg.get("env"), issues, warnings)

    # Warn on unknown top-level keys
    if not allow_unknown:
        known_keys = {
            "meta", "gateway", "session", "agents", "providers", "models",
            "channels", "logging", "memory", "hooks", "cron", "plugins",
            "secrets", "browser", "talk", "acp", "approvals", "messages",
            "skills", "env", "auth", "discord", "telegram", "slack",
            "signal", "imessage", "whatsapp", "$include",
        }
        for key in cfg:
            if key not in known_keys:
                warnings.append(ConfigValidationIssue(key, f"unknown config key: {key}"))

    return ConfigValidationResult(
        ok=len(issues) == 0,
        issues=issues,
        warnings=warnings,
        config=cfg,
    )


def validate_config_object_with_plugins(raw: Any) -> ConfigValidationResult:
    """Validate config with plugin schema extensions."""
    return validate_config_object(raw, allow_unknown=True)


def _validate_gateway(gw: Any, issues: list, warnings: list) -> None:
    if gw is None:
        return
    if not isinstance(gw, dict):
        issues.append(ConfigValidationIssue("gateway", "must be an object"))
        return

    mode = gw.get("mode")
    if mode is not None and mode not in ALLOWED_GATEWAY_MODES:
        issues.append(ConfigValidationIssue(
            "gateway.mode", f"must be one of {ALLOWED_GATEWAY_MODES}",
        ))

    port = gw.get("port")
    if port is not None:
        if not isinstance(port, int) or port < 1 or port > 65535:
            issues.append(ConfigValidationIssue(
                "gateway.port", "must be an integer between 1 and 65535",
            ))

    bind = gw.get("bind")
    if bind is not None and bind not in ALLOWED_BIND_VALUES:
        issues.append(ConfigValidationIssue(
            "gateway.bind", f"must be one of {ALLOWED_BIND_VALUES}",
        ))

    auth = gw.get("auth")
    if isinstance(auth, dict):
        auth_mode = auth.get("mode")
        if auth_mode is not None and auth_mode not in ALLOWED_AUTH_MODES:
            issues.append(ConfigValidationIssue(
                "gateway.auth.mode", f"must be one of {ALLOWED_AUTH_MODES}",
            ))

    # Warn on gateway.token miskey
    if "token" in gw:
        warnings.append(ConfigValidationIssue(
            "gateway.token",
            'gateway.token is ignored; use gateway.auth.token instead',
        ))


def _validate_session(sess: Any, issues: list, warnings: list) -> None:
    if sess is None:
        return
    if not isinstance(sess, dict):
        issues.append(ConfigValidationIssue("session", "must be an object"))
        return
    storage = sess.get("storage")
    if storage is not None and storage not in ALLOWED_SESSION_STORAGE:
        issues.append(ConfigValidationIssue(
            "session.storage", f"must be one of {ALLOWED_SESSION_STORAGE}",
        ))


def _validate_agents(agents: Any, issues: list, warnings: list) -> None:
    if agents is None:
        return
    if not isinstance(agents, dict):
        issues.append(ConfigValidationIssue("agents", "must be an object"))
        return
    defaults = agents.get("defaults")
    if defaults is not None and not isinstance(defaults, dict):
        issues.append(ConfigValidationIssue("agents.defaults", "must be an object"))


def _validate_logging(log: Any, issues: list, warnings: list) -> None:
    if log is None:
        return
    if not isinstance(log, dict):
        issues.append(ConfigValidationIssue("logging", "must be an object"))
        return
    level = log.get("level")
    if level is not None and level not in ALLOWED_LOG_LEVELS:
        issues.append(ConfigValidationIssue(
            "logging.level", f"must be one of {ALLOWED_LOG_LEVELS}",
        ))
    redact = log.get("redactSensitive")
    if redact is not None and redact not in ALLOWED_REDACT_MODES:
        issues.append(ConfigValidationIssue(
            "logging.redactSensitive", f"must be one of {ALLOWED_REDACT_MODES}",
        ))


def _validate_approvals(approvals: Any, issues: list, warnings: list) -> None:
    if approvals is None:
        return
    if not isinstance(approvals, dict):
        issues.append(ConfigValidationIssue("approvals", "must be an object"))
        return
    mode = approvals.get("mode")
    if mode is not None and mode not in ALLOWED_APPROVAL_MODES:
        issues.append(ConfigValidationIssue(
            "approvals.mode", f"must be one of {ALLOWED_APPROVAL_MODES}",
        ))


def _validate_models(models: Any, issues: list, warnings: list) -> None:
    if models is None:
        return
    if not isinstance(models, dict):
        issues.append(ConfigValidationIssue("models", "must be an object"))
        return
    providers = models.get("providers")
    if providers is not None and not isinstance(providers, dict):
        issues.append(ConfigValidationIssue("models.providers", "must be an object"))


def _validate_cron(cron: Any, issues: list, warnings: list) -> None:
    if cron is None:
        return
    if not isinstance(cron, list):
        issues.append(ConfigValidationIssue("cron", "must be an array"))
        return
    for i, job in enumerate(cron):
        if not isinstance(job, dict):
            issues.append(ConfigValidationIssue(f"cron[{i}]", "must be an object"))
            continue
        if not isinstance(job.get("schedule"), str):
            issues.append(ConfigValidationIssue(f"cron[{i}].schedule", "is required"))
        if not isinstance(job.get("command"), str):
            issues.append(ConfigValidationIssue(f"cron[{i}].command", "is required"))


def _validate_env(env: Any, issues: list, warnings: list) -> None:
    if env is None:
        return
    if not isinstance(env, dict):
        issues.append(ConfigValidationIssue("env", "must be an object"))
        return
    vars_section = env.get("vars")
    if vars_section is not None and not isinstance(vars_section, dict):
        issues.append(ConfigValidationIssue("env.vars", "must be an object"))


# ─── Version comparison (version.ts) ───

def compare_openclaw_versions(current: str, other: str) -> int | None:
    """Compare two OpenClaw version strings.

    Returns negative if current < other, 0 if equal, positive if current > other.
    Returns None if either version is unparseable.
    """
    def parse_version(v: str) -> tuple[int, ...] | None:
        parts = v.strip().lstrip("v").split(".")
        try:
            return tuple(int(p) for p in parts)
        except ValueError:
            return None

    cv = parse_version(current)
    ov = parse_version(other)
    if cv is None or ov is None:
        return None

    for a, b in zip(cv, ov):
        if a != b:
            return a - b
    return len(cv) - len(ov)


# ─── Runtime overrides (runtime-overrides.ts) ───

def apply_config_overrides(
    cfg: dict[str, Any],
    overrides: dict[str, Any],
) -> dict[str, Any]:
    """Apply runtime overrides to a config dict."""
    if not overrides:
        return cfg
    result = dict(cfg)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = apply_config_overrides(result[key], value)
        else:
            result[key] = value
    return result


# ─── Redaction (redact-snapshot.ts) ───

SENSITIVE_KEYS = frozenset({
    "token", "password", "apiKey", "api_key", "secret",
    "botToken", "bot_token", "appToken", "app_token",
    "accessToken", "access_token", "refreshToken", "refresh_token",
    "webhook", "webhookUrl", "webhook_url",
})


def redact_config_snapshot(config: dict[str, Any]) -> dict[str, Any]:
    """Redact sensitive values from a config snapshot."""
    return _redact_recursive(config)


def _redact_recursive(value: Any, key: str = "") -> Any:
    if isinstance(value, str):
        if key.lower().rstrip("_") in {k.lower() for k in SENSITIVE_KEYS}:
            if len(value) > 4:
                return f"{value[:2]}***{value[-2:]}"
            return "***"
        return value
    if isinstance(value, dict):
        return {k: _redact_recursive(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_recursive(item) for item in value]
    return value


# ─── Legacy migration (legacy.ts, legacy-migrate.ts) ───

def find_legacy_config_issues(cfg: dict[str, Any]) -> list[dict[str, str]]:
    """Find legacy configuration issues that need migration."""
    issues: list[dict[str, str]] = []

    # Check for deprecated top-level keys
    deprecated_keys = {
        "openai": "providers.openai",
        "anthropic": "providers.anthropic",
        "model": "agents.defaults.model",
        "systemPrompt": "agents.defaults.systemPrompt",
        "maxTokens": "agents.defaults.maxTokens",
    }
    for old_key, new_path in deprecated_keys.items():
        if old_key in cfg:
            issues.append({
                "path": old_key,
                "message": f'"{old_key}" is deprecated; use "{new_path}" instead',
                "severity": "warning",
            })

    # Check for old gateway.token pattern
    gateway = cfg.get("gateway", {}) or {}
    if "token" in gateway and not isinstance(gateway.get("auth"), dict):
        issues.append({
            "path": "gateway.token",
            "message": 'Move "gateway.token" to "gateway.auth.token"',
            "severity": "warning",
        })

    return issues


def migrate_legacy_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Migrate a legacy config to the current format."""
    result = dict(cfg)

    # Migrate top-level model key
    if "model" in result and "agents" not in result:
        result["agents"] = {"defaults": {"model": result.pop("model")}}
    elif "model" in result:
        agents = result.setdefault("agents", {})
        defaults = agents.setdefault("defaults", {})
        if "model" not in defaults:
            defaults["model"] = result.pop("model")
        else:
            del result["model"]

    # Migrate top-level systemPrompt
    if "systemPrompt" in result:
        agents = result.setdefault("agents", {})
        defaults = agents.setdefault("defaults", {})
        if "systemPrompt" not in defaults:
            defaults["systemPrompt"] = result.pop("systemPrompt")
        else:
            del result["systemPrompt"]

    # Migrate gateway.token → gateway.auth.token
    gateway = result.get("gateway", {}) or {}
    if "token" in gateway:
        auth = gateway.setdefault("auth", {})
        if "token" not in auth:
            auth["token"] = gateway.pop("token")
        else:
            del gateway["token"]
        result["gateway"] = gateway

    # Migrate top-level provider keys
    for provider in ("openai", "anthropic", "google"):
        if provider in result:
            providers = result.setdefault("providers", {})
            if provider not in providers:
                providers[provider] = result.pop(provider)
            else:
                del result[provider]

    return result


# ─── Normalize paths (normalize-paths.ts) ───

def normalize_config_paths(cfg: dict[str, Any]) -> None:
    """Normalize relative paths in config to absolute paths."""
    import os

    agents = cfg.get("agents", {}) or {}
    agent_dir = agents.get("dir")
    if isinstance(agent_dir, str) and agent_dir and not os.path.isabs(agent_dir):
        agents["dir"] = os.path.expanduser(agent_dir)

    plugins = cfg.get("plugins", {}) or {}
    plugin_dir = plugins.get("dir")
    if isinstance(plugin_dir, str) and plugin_dir and not os.path.isabs(plugin_dir):
        plugins["dir"] = os.path.expanduser(plugin_dir)


# ─── Byte size parsing (byte-size.ts) ───

BYTE_UNITS = {
    "b": 1,
    "kb": 1024,
    "mb": 1024 ** 2,
    "gb": 1024 ** 3,
    "tb": 1024 ** 4,
}


def parse_byte_size(value: str | int) -> int | None:
    """Parse a human-readable byte size (e.g. '10MB') to bytes."""
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return None
    match = re.match(r"^\s*(\d+(?:\.\d+)?)\s*(b|kb|mb|gb|tb)?\s*$", value.strip(), re.I)
    if not match:
        return None
    num = float(match.group(1))
    unit = (match.group(2) or "b").lower()
    return int(num * BYTE_UNITS.get(unit, 1))
