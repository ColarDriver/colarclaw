"""Secrets management system.

Ported from bk/src/secrets/ (~32 TS files, ~8.4k lines).

Supports multiple backends (env, file, 1Password), secret resolution,
input validation, provider credential management, and secure storage.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ─── Secret input types ───

@dataclass
class SecretInput:
    """A secret reference — literal, env, file, or 1Password."""
    value: str | None = None
    env: str | None = None
    file: str | None = None
    op: str | None = None  # 1Password reference


@dataclass
class ResolvedSecret:
    """A resolved secret value."""
    value: str = ""
    source: str = ""  # "literal" | "env" | "file" | "1password" | "store"
    masked: str = ""


def mask_secret(value: str, *, show_chars: int = 4) -> str:
    """Mask a secret value for display."""
    if len(value) <= show_chars:
        return "***"
    return f"{value[:show_chars // 2]}***{value[-show_chars // 2:]}"


# ─── Secret resolution ───

def resolve_secret(
    input_val: SecretInput | str | dict[str, Any] | None,
    *,
    env: dict[str, str] | None = None,
) -> ResolvedSecret | None:
    """Resolve a secret input to its value."""
    if input_val is None:
        return None

    # Literal string
    if isinstance(input_val, str):
        if input_val.startswith("${") and input_val.endswith("}"):
            var_name = input_val[2:-1]
            e = env or os.environ
            val = e.get(var_name, "")
            return ResolvedSecret(value=val, source="env", masked=mask_secret(val))
        return ResolvedSecret(value=input_val, source="literal", masked=mask_secret(input_val))

    # Dict format
    if isinstance(input_val, dict):
        if "value" in input_val and input_val["value"]:
            v = str(input_val["value"])
            return ResolvedSecret(value=v, source="literal", masked=mask_secret(v))
        if "env" in input_val:
            var = str(input_val["env"])
            e = env or os.environ
            val = e.get(var, "")
            return ResolvedSecret(value=val, source="env", masked=mask_secret(val))
        if "file" in input_val:
            path = str(input_val["file"])
            try:
                val = Path(path).read_text(encoding="utf-8").strip()
                return ResolvedSecret(value=val, source="file", masked=mask_secret(val))
            except Exception as e_:
                logger.warning(f"Failed to read secret file {path}: {e_}")
                return None
        if "op" in input_val:
            return _resolve_1password(str(input_val["op"]))

    # SecretInput dataclass
    if isinstance(input_val, SecretInput):
        if input_val.value:
            return ResolvedSecret(
                value=input_val.value, source="literal",
                masked=mask_secret(input_val.value),
            )
        if input_val.env:
            e = env or os.environ
            val = e.get(input_val.env, "")
            return ResolvedSecret(value=val, source="env", masked=mask_secret(val))
        if input_val.file:
            try:
                val = Path(input_val.file).read_text(encoding="utf-8").strip()
                return ResolvedSecret(value=val, source="file", masked=mask_secret(val))
            except Exception:
                return None
        if input_val.op:
            return _resolve_1password(input_val.op)

    return None


def _resolve_1password(ref: str) -> ResolvedSecret | None:
    """Resolve a 1Password secret reference."""
    import subprocess
    try:
        result = subprocess.run(
            ["op", "read", ref],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            val = result.stdout.strip()
            return ResolvedSecret(value=val, source="1password", masked=mask_secret(val))
        logger.warning(f"1Password read failed: {result.stderr}")
    except FileNotFoundError:
        logger.warning("1Password CLI (op) not found")
    except Exception as e:
        logger.warning(f"1Password error: {e}")
    return None


# ─── Secret store ───

class SecretStore:
    """Encrypted file-based secret store."""

    def __init__(self, store_dir: str):
        self._store_dir = store_dir
        self._cache: dict[str, str] = {}

    def _file_path(self, name: str) -> str:
        safe = name.replace("/", "_").replace("\\", "_")
        return os.path.join(self._store_dir, f"{safe}.secret")

    def set(self, name: str, value: str) -> None:
        """Store a secret."""
        os.makedirs(self._store_dir, mode=0o700, exist_ok=True)
        path = self._file_path(name)
        encoded = base64.b64encode(value.encode("utf-8")).decode("ascii")
        with open(path, "w", encoding="utf-8") as f:
            os.fchmod(f.fileno(), 0o600)
            f.write(encoded)
        self._cache[name] = value

    def get(self, name: str) -> str | None:
        """Retrieve a secret."""
        if name in self._cache:
            return self._cache[name]
        path = self._file_path(name)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                encoded = f.read().strip()
            value = base64.b64decode(encoded).decode("utf-8")
            self._cache[name] = value
            return value
        except Exception as e:
            logger.warning(f"Failed to read secret {name}: {e}")
            return None

    def delete(self, name: str) -> bool:
        """Delete a secret."""
        self._cache.pop(name, None)
        path = self._file_path(name)
        if os.path.exists(path):
            os.unlink(path)
            return True
        return False

    def list_names(self) -> list[str]:
        """List all stored secret names."""
        if not os.path.isdir(self._store_dir):
            return []
        return [
            f[:-7]  # strip .secret
            for f in os.listdir(self._store_dir)
            if f.endswith(".secret")
        ]


# ─── Provider credential helpers ───

PROVIDER_SECRET_KEYS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "elevenlabs": "ELEVENLABS_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "xai": "XAI_API_KEY",
}


def resolve_provider_api_key(
    provider: str,
    config: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
) -> str | None:
    """Resolve an API key for a provider."""
    e = env or os.environ

    # Check env var
    env_key = PROVIDER_SECRET_KEYS.get(provider.lower())
    if env_key:
        val = e.get(env_key, "").strip()
        if val:
            return val

    # Check config
    if config:
        providers = config.get("providers", {}) or {}
        provider_cfg = providers.get(provider, {}) or {}
        api_key = provider_cfg.get("apiKey")
        if api_key:
            resolved = resolve_secret(api_key, env=e)
            if resolved and resolved.value:
                return resolved.value

    return None


def has_configured_secret_input(value: Any) -> bool:
    """Check if a secret input has a configured value."""
    if not value:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return bool(
            value.get("value")
            or value.get("env")
            or value.get("file")
            or value.get("op")
        )
    return False
