"""CLI backends — ported from bk/src/agents/cli-backends.ts.

Resolution and merging of CLI backend configurations (Claude, Codex, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .model_selection import normalize_provider_id


@dataclass
class CliBackendReliabilityWatchdog:
    fresh: dict[str, Any] = field(default_factory=dict)
    resume: dict[str, Any] = field(default_factory=dict)


@dataclass
class CliBackendReliability:
    watchdog: CliBackendReliabilityWatchdog = field(default_factory=CliBackendReliabilityWatchdog)


@dataclass
class CliBackendConfig:
    command: str = ""
    args: list[str] | None = None
    resume_args: list[str] | None = None
    output: str = "json"
    resume_output: str | None = None
    input: str = "arg"
    model_arg: str | None = None
    model_aliases: dict[str, str] | None = None
    session_arg: str | None = None
    session_mode: str | None = None
    session_id_fields: list[str] | None = None
    session_args: list[str] | None = None
    system_prompt_arg: str | None = None
    system_prompt_mode: str | None = None
    system_prompt_when: str | None = None
    image_arg: str | None = None
    image_mode: str | None = None
    clear_env: list[str] | None = None
    env: dict[str, str] | None = None
    reliability: CliBackendReliability | None = None
    serialize: bool = False


@dataclass
class ResolvedCliBackend:
    id: str
    config: CliBackendConfig


CLAUDE_MODEL_ALIASES: dict[str, str] = {
    "opus": "opus", "opus-4.6": "opus", "opus-4.5": "opus", "opus-4": "opus",
    "claude-opus-4-6": "opus", "claude-opus-4-5": "opus", "claude-opus-4": "opus",
    "sonnet": "sonnet", "sonnet-4.6": "sonnet", "sonnet-4.5": "sonnet",
    "sonnet-4.1": "sonnet", "sonnet-4.0": "sonnet",
    "claude-sonnet-4-6": "sonnet", "claude-sonnet-4-5": "sonnet",
    "claude-sonnet-4-1": "sonnet", "claude-sonnet-4-0": "sonnet",
    "haiku": "haiku", "haiku-3.5": "haiku", "claude-haiku-3-5": "haiku",
}

_CLAUDE_LEGACY_SKIP_PERMISSIONS_ARG = "--dangerously-skip-permissions"
_CLAUDE_PERMISSION_MODE_ARG = "--permission-mode"
_CLAUDE_BYPASS_PERMISSIONS_MODE = "bypassPermissions"

CLI_FRESH_WATCHDOG_DEFAULTS: dict[str, Any] = {}
CLI_RESUME_WATCHDOG_DEFAULTS: dict[str, Any] = {}

DEFAULT_CLAUDE_BACKEND = CliBackendConfig(
    command="claude",
    args=["-p", "--output-format", "json", "--permission-mode", "bypassPermissions"],
    resume_args=[
        "-p", "--output-format", "json", "--permission-mode", "bypassPermissions",
        "--resume", "{sessionId}",
    ],
    output="json",
    input="arg",
    model_arg="--model",
    model_aliases=dict(CLAUDE_MODEL_ALIASES),
    session_arg="--session-id",
    session_mode="always",
    session_id_fields=["session_id", "sessionId", "conversation_id", "conversationId"],
    system_prompt_arg="--append-system-prompt",
    system_prompt_mode="append",
    system_prompt_when="first",
    clear_env=["ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY_OLD"],
    reliability=CliBackendReliability(
        watchdog=CliBackendReliabilityWatchdog(
            fresh=dict(CLI_FRESH_WATCHDOG_DEFAULTS),
            resume=dict(CLI_RESUME_WATCHDOG_DEFAULTS),
        ),
    ),
    serialize=True,
)

DEFAULT_CODEX_BACKEND = CliBackendConfig(
    command="codex",
    args=[
        "exec", "--json", "--color", "never",
        "--sandbox", "workspace-write", "--skip-git-repo-check",
    ],
    resume_args=[
        "exec", "resume", "{sessionId}", "--color", "never",
        "--sandbox", "workspace-write", "--skip-git-repo-check",
    ],
    output="jsonl",
    resume_output="text",
    input="arg",
    model_arg="--model",
    session_id_fields=["thread_id"],
    session_mode="existing",
    image_arg="--image",
    image_mode="repeat",
    reliability=CliBackendReliability(
        watchdog=CliBackendReliabilityWatchdog(
            fresh=dict(CLI_FRESH_WATCHDOG_DEFAULTS),
            resume=dict(CLI_RESUME_WATCHDOG_DEFAULTS),
        ),
    ),
    serialize=True,
)


def _normalize_backend_key(key: str) -> str:
    return normalize_provider_id(key)


def _pick_backend_config(
    config: dict[str, Any],
    normalized_id: str,
) -> CliBackendConfig | None:
    for key, entry in config.items():
        if _normalize_backend_key(key) == normalized_id:
            if isinstance(entry, CliBackendConfig):
                return entry
            # Support dict-based config
            return CliBackendConfig(**entry) if isinstance(entry, dict) else None
    return None


def _merge_backend_config(base: CliBackendConfig, override: CliBackendConfig | None) -> CliBackendConfig:
    if override is None:
        return CliBackendConfig(
            command=base.command, args=list(base.args or []),
            resume_args=list(base.resume_args or []) if base.resume_args else None,
            output=base.output, resume_output=base.resume_output,
            input=base.input, model_arg=base.model_arg,
            model_aliases=dict(base.model_aliases or {}),
            session_arg=base.session_arg, session_mode=base.session_mode,
            session_id_fields=list(base.session_id_fields or []) if base.session_id_fields else None,
            session_args=list(base.session_args or []) if base.session_args else None,
            system_prompt_arg=base.system_prompt_arg,
            system_prompt_mode=base.system_prompt_mode,
            system_prompt_when=base.system_prompt_when,
            image_arg=base.image_arg, image_mode=base.image_mode,
            clear_env=list(base.clear_env or []),
            env=dict(base.env or {}),
            reliability=base.reliability, serialize=base.serialize,
        )

    merged_env = {**(base.env or {}), **(override.env or {})}
    merged_aliases = {**(base.model_aliases or {}), **(override.model_aliases or {})}
    merged_clear_env = list(set((base.clear_env or []) + (override.clear_env or [])))

    base_fresh = base.reliability.watchdog.fresh if base.reliability else {}
    base_resume = base.reliability.watchdog.resume if base.reliability else {}
    ov_fresh = override.reliability.watchdog.fresh if override.reliability else {}
    ov_resume = override.reliability.watchdog.resume if override.reliability else {}

    return CliBackendConfig(
        command=override.command or base.command,
        args=override.args if override.args is not None else base.args,
        resume_args=override.resume_args if override.resume_args is not None else base.resume_args,
        output=override.output or base.output,
        resume_output=override.resume_output or base.resume_output,
        input=override.input or base.input,
        model_arg=override.model_arg or base.model_arg,
        model_aliases=merged_aliases,
        session_arg=override.session_arg or base.session_arg,
        session_mode=override.session_mode or base.session_mode,
        session_id_fields=override.session_id_fields or base.session_id_fields,
        session_args=override.session_args or base.session_args,
        system_prompt_arg=override.system_prompt_arg or base.system_prompt_arg,
        system_prompt_mode=override.system_prompt_mode or base.system_prompt_mode,
        system_prompt_when=override.system_prompt_when or base.system_prompt_when,
        image_arg=override.image_arg or base.image_arg,
        image_mode=override.image_mode or base.image_mode,
        clear_env=merged_clear_env,
        env=merged_env,
        reliability=CliBackendReliability(
            watchdog=CliBackendReliabilityWatchdog(
                fresh={**base_fresh, **ov_fresh},
                resume={**base_resume, **ov_resume},
            ),
        ),
        serialize=override.serialize if override.serialize else base.serialize,
    )


def _normalize_claude_permission_args(args: list[str] | None) -> list[str] | None:
    if args is None:
        return args
    normalized: list[str] = []
    saw_legacy_skip = False
    has_permission_mode = False
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == _CLAUDE_LEGACY_SKIP_PERMISSIONS_ARG:
            saw_legacy_skip = True
            i += 1
            continue
        if arg == _CLAUDE_PERMISSION_MODE_ARG:
            has_permission_mode = True
            normalized.append(arg)
            if i + 1 < len(args):
                normalized.append(args[i + 1])
                i += 2
            else:
                i += 1
            continue
        if arg.startswith(f"{_CLAUDE_PERMISSION_MODE_ARG}="):
            has_permission_mode = True
        normalized.append(arg)
        i += 1
    if saw_legacy_skip and not has_permission_mode:
        normalized.extend([_CLAUDE_PERMISSION_MODE_ARG, _CLAUDE_BYPASS_PERMISSIONS_MODE])
    return normalized


def _normalize_claude_backend_config(config: CliBackendConfig) -> CliBackendConfig:
    config.args = _normalize_claude_permission_args(config.args)
    config.resume_args = _normalize_claude_permission_args(config.resume_args)
    return config


def resolve_cli_backend_ids(cfg: Any | None = None) -> set[str]:
    ids = {_normalize_backend_key("claude-cli"), _normalize_backend_key("codex-cli")}
    if cfg:
        configured = getattr(cfg, "agents", {})
        if isinstance(configured, dict):
            defaults = configured.get("defaults", {})
            backends = defaults.get("cliBackends", {}) if isinstance(defaults, dict) else {}
        else:
            backends = getattr(getattr(configured, "defaults", None), "cli_backends", {}) or {}
        if isinstance(backends, dict):
            for key in backends:
                ids.add(_normalize_backend_key(key))
    return ids


def resolve_cli_backend_config(
    provider: str,
    cfg: Any | None = None,
) -> ResolvedCliBackend | None:
    normalized = _normalize_backend_key(provider)
    configured: dict[str, Any] = {}
    if cfg:
        try:
            agents = getattr(cfg, "agents", {})
            if isinstance(agents, dict):
                defaults = agents.get("defaults", {})
                configured = defaults.get("cliBackends", {}) if isinstance(defaults, dict) else {}
            else:
                configured = getattr(getattr(agents, "defaults", None), "cli_backends", {}) or {}
        except Exception:
            configured = {}

    override = _pick_backend_config(configured, normalized) if configured else None

    if normalized == "claude-cli":
        merged = _merge_backend_config(DEFAULT_CLAUDE_BACKEND, override)
        config = _normalize_claude_backend_config(merged)
        command = (config.command or "").strip()
        if not command:
            return None
        config.command = command
        return ResolvedCliBackend(id=normalized, config=config)

    if normalized == "codex-cli":
        merged = _merge_backend_config(DEFAULT_CODEX_BACKEND, override)
        command = (merged.command or "").strip()
        if not command:
            return None
        merged.command = command
        return ResolvedCliBackend(id=normalized, config=merged)

    if not override:
        return None
    command = (override.command or "").strip()
    if not command:
        return None
    override.command = command
    return ResolvedCliBackend(id=normalized, config=override)
