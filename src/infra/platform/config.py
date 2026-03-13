"""Infra config — ported from bk/src/infra/config-*.ts files,
settings.ts, profile.ts, contact-group.ts, locale.ts, features.ts.

Configuration management: config loading, profile resolution,
contact groups, locale/i18n, feature flags.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

logger = logging.getLogger("infra.config")


# ─── config-load.ts / config-merge.ts ───

def resolve_config_dir(env: dict[str, str] | None = None) -> str:
    e = env or os.environ
    explicit = e.get("OPENCLAW_CONFIG_DIR", "").strip()
    if explicit:
        return os.path.abspath(explicit)
    return os.path.join(str(Path.home()), ".openclaw")


def load_config_file(path: str) -> dict[str, Any]:
    """Load a JSON config file."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_config_file(path: str, data: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def merge_config(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge configs, override wins."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_config(result[key], value)
        else:
            result[key] = value
    return result


# ─── config set/get ───

def config_get(path: str, key: str, config_file: str | None = None) -> Any:
    """Get a nested config value using dot-notation key."""
    cfg_path = config_file or os.path.join(resolve_config_dir(), "config.json")
    data = load_config_file(cfg_path)
    keys = key.strip().split(".")
    current = data
    for k in keys:
        if isinstance(current, dict) and k in current:
            current = current[k]
        else:
            return None
    return current


def config_set(key: str, value: Any, config_file: str | None = None) -> None:
    """Set a nested config value using dot-notation key."""
    cfg_path = config_file or os.path.join(resolve_config_dir(), "config.json")
    data = load_config_file(cfg_path)
    keys = key.strip().split(".")
    current = data
    for k in keys[:-1]:
        if k not in current or not isinstance(current[k], dict):
            current[k] = {}
        current = current[k]
    current[keys[-1]] = value
    save_config_file(cfg_path, data)


# ─── profile.ts ───

@dataclass
class Profile:
    name: str = "default"
    display_name: str | None = None
    config: dict[str, Any] = field(default_factory=dict)


def resolve_profile_name(env: dict[str, str] | None = None) -> str:
    e = env or os.environ
    return e.get("OPENCLAW_PROFILE", "").strip() or "default"


def load_profile(name: str | None = None) -> Profile:
    """Load a named profile."""
    profile_name = name or resolve_profile_name()
    config_dir = resolve_config_dir()
    profiles_file = os.path.join(config_dir, "profiles.json")
    data = load_config_file(profiles_file)
    profiles = data.get("profiles", {})
    profile_data = profiles.get(profile_name, {})
    return Profile(
        name=profile_name,
        display_name=profile_data.get("displayName"),
        config=profile_data.get("config", {}),
    )


def save_profile(profile: Profile) -> None:
    config_dir = resolve_config_dir()
    profiles_file = os.path.join(config_dir, "profiles.json")
    data = load_config_file(profiles_file)
    if "profiles" not in data:
        data["profiles"] = {}
    data["profiles"][profile.name] = {
        "displayName": profile.display_name,
        "config": profile.config,
    }
    save_config_file(profiles_file, data)


def list_profiles() -> list[str]:
    config_dir = resolve_config_dir()
    profiles_file = os.path.join(config_dir, "profiles.json")
    data = load_config_file(profiles_file)
    return list(data.get("profiles", {}).keys())


# ─── contact-group.ts ───

@dataclass
class ContactGroup:
    name: str = ""
    members: list[str] = field(default_factory=list)
    description: str | None = None
    channel: str | None = None


def load_contact_groups(config_dir: str | None = None) -> list[ContactGroup]:
    """Load contact groups from config."""
    cfg_dir = config_dir or resolve_config_dir()
    groups_file = os.path.join(cfg_dir, "contact-groups.json")
    data = load_config_file(groups_file)
    groups: list[ContactGroup] = []
    for item in data.get("groups", []):
        groups.append(ContactGroup(
            name=item.get("name", ""),
            members=item.get("members", []),
            description=item.get("description"),
            channel=item.get("channel"),
        ))
    return groups


def save_contact_groups(groups: list[ContactGroup], config_dir: str | None = None) -> None:
    cfg_dir = config_dir or resolve_config_dir()
    groups_file = os.path.join(cfg_dir, "contact-groups.json")
    data = {
        "groups": [
            {"name": g.name, "members": g.members,
             "description": g.description, "channel": g.channel}
            for g in groups
        ]
    }
    save_config_file(groups_file, data)


def find_contact_group(name: str, config_dir: str | None = None) -> ContactGroup | None:
    groups = load_contact_groups(config_dir)
    name_lower = name.strip().lower()
    for group in groups:
        if group.name.lower() == name_lower:
            return group
    return None


# ─── locale.ts ───

def resolve_locale(env: dict[str, str] | None = None) -> str:
    """Resolve the user's locale."""
    e = env or os.environ
    explicit = e.get("OPENCLAW_LOCALE", "").strip()
    if explicit:
        return explicit
    for key in ("LC_ALL", "LC_MESSAGES", "LANG"):
        val = e.get(key, "").strip()
        if val:
            # Strip charset suffix
            return val.split(".")[0].replace("_", "-")
    return "en-US"


def is_cjk_locale(locale: str | None = None) -> bool:
    loc = (locale or resolve_locale()).lower()
    return any(loc.startswith(prefix) for prefix in ("zh", "ja", "ko"))


# ─── features.ts ───

@dataclass
class FeatureFlags:
    flags: dict[str, bool] = field(default_factory=dict)


_feature_flags: dict[str, bool] = {}


def set_feature_flag(name: str, enabled: bool = True) -> None:
    _feature_flags[name] = enabled


def is_feature_enabled(name: str, default: bool = False) -> bool:
    """Check if a feature flag is enabled."""
    # Check env override first
    env_key = f"OPENCLAW_FEATURE_{name.upper().replace('-', '_')}"
    env_val = os.environ.get(env_key, "").strip().lower()
    if env_val in ("true", "1", "yes"):
        return True
    if env_val in ("false", "0", "no"):
        return False
    return _feature_flags.get(name, default)


def get_all_feature_flags() -> dict[str, bool]:
    return dict(_feature_flags)


def clear_feature_flags() -> None:
    _feature_flags.clear()


# ─── settings.ts ───

@dataclass
class Settings:
    gateway_port: int = 18789
    gateway_mode: str = "local"  # "local" | "tailscale" | "cloudflare"
    gateway_bind: str = "loopback"
    default_channel: str | None = None
    default_model: str | None = None
    verbose: bool = False
    log_level: str = "info"
    theme: str = "auto"


def load_settings(config_dir: str | None = None) -> Settings:
    """Load settings from config."""
    cfg_dir = config_dir or resolve_config_dir()
    data = load_config_file(os.path.join(cfg_dir, "config.json"))
    gateway = data.get("gateway", {})
    return Settings(
        gateway_port=gateway.get("port", 18789),
        gateway_mode=gateway.get("mode", "local"),
        gateway_bind=gateway.get("bind", "loopback"),
        default_channel=data.get("defaults", {}).get("channel"),
        default_model=data.get("defaults", {}).get("model"),
        verbose=data.get("verbose", False),
        log_level=data.get("logLevel", "info"),
        theme=data.get("theme", "auto"),
    )
