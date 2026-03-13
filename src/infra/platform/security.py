"""Infra security — ported from bk/src/infra/host-env-security.ts,
token-sanitize.ts, credential-guard.ts, fingerprint-detection.ts,
content-guard.ts, injection-detection.ts, session-token.ts, api-key-validation.ts.

Security utilities: credential guarding, injection detection, token
sanitization, content guards, session tokens, API key validation.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("infra.security")


# ─── token-sanitize.ts ───

# Patterns that look like API keys / tokens
_API_KEY_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),  # OpenAI/Anthropic style
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),  # Google API key
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),    # GitHub PAT
    re.compile(r"gho_[a-zA-Z0-9]{36}"),    # GitHub OAuth
    re.compile(r"xoxb-[0-9]+-[a-zA-Z0-9]+"),  # Slack bot token
    re.compile(r"xoxp-[0-9]+-[a-zA-Z0-9]+"),  # Slack user token
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key
    re.compile(r"[0-9a-f]{64}"),  # generic hex token (64 chars)
]


def sanitize_token(text: str) -> str:
    """Redact tokens/API keys from text."""
    result = text
    for pattern in _API_KEY_PATTERNS:
        result = pattern.sub(lambda m: m.group(0)[:4] + "…" + m.group(0)[-4:], result)
    return result


def mask_api_key(key: str | None) -> str:
    """Mask an API key for display."""
    if not key or len(key) < 8:
        return "***"
    return f"{key[:4]}…{key[-4:]}"


# ─── credential-guard.ts ───

_CREDENTIAL_ENV_KEYS = {
    "ANTHROPIC_API_KEY", "CLAUDE_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY", "GOOGLE_API_KEY",
    "GITHUB_TOKEN", "GITHUB_COPILOT_TOKEN",
    "MINIMAX_API_KEY",
    "ZAI_API_KEY", "Z_AI_API_KEY",
    "OPENCLAW_SESSION_TOKEN",
    "OPENCLAW_API_KEY",
    "AWS_SECRET_ACCESS_KEY",
    "SLACK_BOT_TOKEN",
    "DISCORD_BOT_TOKEN",
    "TELEGRAM_BOT_TOKEN",
}


def is_credential_env_key(key: str) -> bool:
    """Check if an env key is a credential key."""
    return key in _CREDENTIAL_ENV_KEYS or any(
        pattern in key.upper() for pattern in ("_KEY", "_TOKEN", "_SECRET", "_PASSWORD", "CREDENTIAL")
    )


def sanitize_env_for_display(env: dict[str, str] | None = None) -> dict[str, str]:
    """Sanitize environment dict for display, masking credentials."""
    source = env or dict(os.environ)
    result: dict[str, str] = {}
    for key, value in source.items():
        if is_credential_env_key(key):
            result[key] = mask_api_key(value)
        else:
            result[key] = value
    return result


# ─── fingerprint-detection.ts ───

_FINGERPRINT_PATTERNS = [
    re.compile(r"(?:what|who)\s+(?:am\s+i|is\s+(?:this|my))", re.I),
    re.compile(r"system\s+prompt", re.I),
    re.compile(r"reveal\s+(?:your|the)\s+(?:instructions|system)", re.I),
    re.compile(r"repeat\s+(?:everything|all)\s+(?:above|before)", re.I),
    re.compile(r"ignore\s+(?:previous|above)\s+instructions", re.I),
]


def detect_fingerprint_attempt(text: str) -> bool:
    """Detect prompt injection/fingerprinting attempts."""
    return any(p.search(text) for p in _FINGERPRINT_PATTERNS)


# ─── injection-detection.ts ───

_INJECTION_PATTERNS = [
    re.compile(r"<\s*/?\s*system\s*>", re.I),
    re.compile(r"<\s*/?\s*assistant\s*>", re.I),
    re.compile(r"<\s*/?\s*user\s*>", re.I),
    re.compile(r"\[INST\]", re.I),
    re.compile(r"\[/INST\]", re.I),
    re.compile(r"<<SYS>>", re.I),
    re.compile(r"<</SYS>>", re.I),
    re.compile(r"Human:", re.I),
    re.compile(r"Assistant:", re.I),
]


def detect_injection(text: str) -> list[str]:
    """Detect potential prompt injection patterns. Returns matched pattern names."""
    matches: list[str] = []
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            matches.append(pattern.pattern)
    return matches


def is_potentially_injected(text: str) -> bool:
    return len(detect_injection(text)) > 0


# ─── content-guard.ts ───

@dataclass
class ContentGuardResult:
    allowed: bool = True
    reason: str = ""
    risk_level: str = "none"  # "none" | "low" | "medium" | "high"


def check_content_guard(
    content: str,
    check_injection: bool = True,
    check_fingerprint: bool = True,
    max_length: int = 100_000,
) -> ContentGuardResult:
    """Check content for security issues."""
    if len(content) > max_length:
        return ContentGuardResult(
            allowed=False,
            reason=f"Content too long ({len(content)} > {max_length})",
            risk_level="medium",
        )
    if check_injection:
        injections = detect_injection(content)
        if injections:
            return ContentGuardResult(
                allowed=False,
                reason=f"Potential injection detected: {', '.join(injections[:3])}",
                risk_level="high",
            )
    if check_fingerprint:
        if detect_fingerprint_attempt(content):
            return ContentGuardResult(
                allowed=True,  # fingerprinting is suspicious but allowed
                reason="Possible fingerprinting attempt",
                risk_level="low",
            )
    return ContentGuardResult()


# ─── session-token.ts ───

def generate_session_token(length: int = 48) -> str:
    """Generate a secure session token."""
    return secrets.token_urlsafe(length)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def verify_session_token(token: str, token_hash: str) -> bool:
    return hashlib.sha256(token.encode()).hexdigest() == token_hash


# ─── api-key-validation.ts ───

_API_KEY_VALIDATION_RULES: dict[str, re.Pattern[str]] = {
    "claude": re.compile(r"^sk-ant-[a-zA-Z0-9_-]{40,}$"),
    "anthropic": re.compile(r"^sk-ant-[a-zA-Z0-9_-]{40,}$"),
    "openai": re.compile(r"^sk-[a-zA-Z0-9]{20,}$"),
    "gemini": re.compile(r"^AIza[0-9A-Za-z_-]{35}$"),
    "github": re.compile(r"^gh[ps]_[a-zA-Z0-9]{36}$"),
    "minimax": re.compile(r"^eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+$"),
}


def validate_api_key_format(provider: str, key: str) -> bool:
    """Validate API key format for a provider."""
    from ..session.provider_usage import normalize_provider_name
    normalized = normalize_provider_name(provider)
    pattern = _API_KEY_VALIDATION_RULES.get(normalized)
    if not pattern:
        return len(key) >= 10  # Generic: at least 10 chars
    return bool(pattern.match(key))


def detect_api_key_provider(key: str) -> str | None:
    """Detect which provider an API key belongs to."""
    for provider, pattern in _API_KEY_VALIDATION_RULES.items():
        if pattern.match(key):
            return provider
    return None
