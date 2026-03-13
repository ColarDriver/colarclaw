"""Secrets — extended: runtime config collectors, resolve, apply, audit.

Ported from bk/src/secrets/ remaining:
runtime-config-collectors-channels.ts (~1044行),
configure.ts (~977行), resolve.ts (~952行),
apply.ts (~777行), target-registry-data.ts (~749行),
audit.ts (~689行), runtime-config-collectors-core.ts (~406行).
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── Secret target registry ───

@dataclass
class SecretTarget:
    """Defines where a secret can be configured."""
    key: str = ""
    label: str = ""
    env_var: str = ""
    config_path: str = ""
    provider: str = ""
    required: bool = False
    sensitive: bool = True


SECRET_TARGETS = [
    SecretTarget(key="anthropic.apiKey", label="Anthropic API Key",
                 env_var="ANTHROPIC_API_KEY", config_path="providers.anthropic.apiKey",
                 provider="anthropic", required=False),
    SecretTarget(key="openai.apiKey", label="OpenAI API Key",
                 env_var="OPENAI_API_KEY", config_path="providers.openai.apiKey",
                 provider="openai"),
    SecretTarget(key="google.apiKey", label="Google AI API Key",
                 env_var="GEMINI_API_KEY", config_path="providers.google.apiKey",
                 provider="google"),
    SecretTarget(key="openrouter.apiKey", label="OpenRouter API Key",
                 env_var="OPENROUTER_API_KEY", config_path="providers.openrouter.apiKey",
                 provider="openrouter"),
    SecretTarget(key="xai.apiKey", label="xAI API Key",
                 env_var="XAI_API_KEY", config_path="providers.xai.apiKey",
                 provider="xai"),
    SecretTarget(key="elevenlabs.apiKey", label="ElevenLabs API Key",
                 env_var="ELEVENLABS_API_KEY", config_path="providers.elevenlabs.apiKey",
                 provider="elevenlabs"),
    SecretTarget(key="discord.botToken", label="Discord Bot Token",
                 env_var="DISCORD_BOT_TOKEN", config_path="discord.botToken",
                 provider="discord"),
    SecretTarget(key="telegram.botToken", label="Telegram Bot Token",
                 env_var="TELEGRAM_BOT_TOKEN", config_path="telegram.botToken",
                 provider="telegram"),
    SecretTarget(key="slack.botToken", label="Slack Bot Token",
                 env_var="SLACK_BOT_TOKEN", config_path="slack.botToken",
                 provider="slack"),
    SecretTarget(key="slack.appToken", label="Slack App Token",
                 env_var="SLACK_APP_TOKEN", config_path="slack.appToken",
                 provider="slack"),
    SecretTarget(key="line.channelAccessToken", label="LINE Channel Token",
                 env_var="LINE_CHANNEL_ACCESS_TOKEN", config_path="line.channelAccessToken",
                 provider="line"),
]


def get_all_secret_targets() -> list[SecretTarget]:
    return list(SECRET_TARGETS)


def get_secret_target(key: str) -> SecretTarget | None:
    return next((t for t in SECRET_TARGETS if t.key == key), None)


# ─── Runtime config collectors ───

def collect_core_secrets(config: dict[str, Any]) -> dict[str, str]:
    """Collect core secrets from config and environment."""
    secrets_found: dict[str, str] = {}
    for target in SECRET_TARGETS:
        if not target.provider or target.provider in ("discord", "telegram", "slack", "line"):
            continue
        # Check env
        val = os.environ.get(target.env_var, "")
        if val:
            secrets_found[target.key] = val
            continue
        # Check config path
        val = _get_nested(config, target.config_path)
        if val and isinstance(val, str) and not val.startswith("${"):
            secrets_found[target.key] = val
    return secrets_found


def collect_channel_secrets(config: dict[str, Any]) -> dict[str, str]:
    """Collect channel-specific secrets."""
    secrets_found: dict[str, str] = {}
    for target in SECRET_TARGETS:
        if target.provider not in ("discord", "telegram", "slack", "line"):
            continue
        val = os.environ.get(target.env_var, "")
        if val:
            secrets_found[target.key] = val
            continue
        val = _get_nested(config, target.config_path)
        if val and isinstance(val, str) and not val.startswith("${"):
            secrets_found[target.key] = val
    return secrets_found


def _get_nested(d: dict[str, Any], path: str) -> Any:
    """Get a nested value from a dict using dot path."""
    parts = path.split(".")
    current: Any = d
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


# ─── Secret resolution (full pipeline) ───

def resolve_all_secrets(config: dict[str, Any]) -> dict[str, str]:
    """Resolve all configured secrets."""
    from . import resolve_secret
    results: dict[str, str] = {}
    for target in SECRET_TARGETS:
        # Try env first
        env_val = os.environ.get(target.env_var, "")
        if env_val:
            results[target.key] = env_val
            continue
        # Try config
        cfg_val = _get_nested(config, target.config_path)
        if cfg_val:
            resolved = resolve_secret(cfg_val)
            if resolved and resolved.value:
                results[target.key] = resolved.value
    return results


# ─── Secret apply ───

def apply_secrets_to_env(secrets: dict[str, str]) -> None:
    """Apply resolved secrets to environment variables."""
    target_map = {t.key: t for t in SECRET_TARGETS}
    for key, value in secrets.items():
        target = target_map.get(key)
        if target and target.env_var:
            os.environ[target.env_var] = value


# ─── Secret audit ───

@dataclass
class SecretAuditEntry:
    target_key: str = ""
    source: str = ""  # "env" | "config" | "store" | "1password"
    is_set: bool = False
    is_valid_format: bool = True
    masked_value: str = ""
    timestamp: str = ""


def audit_secrets(config: dict[str, Any]) -> list[SecretAuditEntry]:
    """Audit all configured secrets."""
    from . import mask_secret
    entries = []
    for target in SECRET_TARGETS:
        entry = SecretAuditEntry(target_key=target.key)
        
        # Check env
        env_val = os.environ.get(target.env_var, "")
        if env_val:
            entry.source = "env"
            entry.is_set = True
            entry.masked_value = mask_secret(env_val)
            entry.is_valid_format = _validate_key_format(target.provider, env_val)
        else:
            # Check config
            cfg_val = _get_nested(config, target.config_path)
            if cfg_val and isinstance(cfg_val, str):
                if cfg_val.startswith("${"):
                    entry.source = "env-ref"
                    entry.is_set = False
                else:
                    entry.source = "config"
                    entry.is_set = True
                    entry.masked_value = mask_secret(cfg_val)
            elif isinstance(cfg_val, dict):
                if cfg_val.get("op"):
                    entry.source = "1password"
                    entry.is_set = True
                elif cfg_val.get("file"):
                    entry.source = "file"
                    entry.is_set = True
        
        entry.timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        entries.append(entry)
    
    return entries


def _validate_key_format(provider: str, key: str) -> bool:
    """Basic format validation for API keys."""
    if provider == "anthropic":
        return key.startswith("sk-ant-") and len(key) > 20
    if provider == "openai":
        return key.startswith("sk-") and len(key) > 20
    if provider == "discord":
        return "." in key and len(key) > 50
    return len(key) > 10


# ─── Configure secrets interactively ───

async def configure_secrets_interactive(config: dict[str, Any]) -> dict[str, str]:
    """Interactive secret configuration."""
    import getpass
    
    audit = audit_secrets(config)
    new_secrets: dict[str, str] = {}
    
    for entry in audit:
        target = get_secret_target(entry.target_key)
        if not target:
            continue
        
        status = "✅" if entry.is_set else "❌"
        print(f"  {status} {target.label} ({target.env_var})")
        
        if not entry.is_set:
            try:
                value = getpass.getpass(f"    Enter {target.label}: ").strip()
                if value:
                    new_secrets[target.key] = value
            except (EOFError, KeyboardInterrupt):
                break
    
    return new_secrets
