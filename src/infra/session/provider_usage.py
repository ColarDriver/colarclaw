"""Infra provider usage — ported from bk/src/infra/provider-usage.*.ts (16 files).

Provider usage tracking: auth, fetching from providers (Claude, Codex, Gemini,
Copilot, Minimax, ZAI), formatting, loading, types.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("infra.provider_usage")


# ─── provider-usage.types.ts ───

@dataclass
class ProviderUsageEntry:
    provider: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_tokens: int = 0
    cost: float | None = None
    timestamp: float = 0.0


@dataclass
class ProviderUsageSummary:
    provider: str = ""
    total_input: int = 0
    total_output: int = 0
    total_cache_read: int = 0
    total_cache_write: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    entry_count: int = 0
    models: list[str] = field(default_factory=list)


# ─── provider-usage.shared.ts ───

def normalize_provider_name(provider: str | None) -> str:
    """Normalize provider name to lowercase canonical form."""
    if not provider:
        return "unknown"
    cleaned = provider.strip().lower()
    ALIASES: dict[str, str] = {
        "anthropic": "claude",
        "openai": "openai",
        "google": "gemini",
        "google-gemini": "gemini",
        "github-copilot": "copilot",
        "minimax": "minimax",
        "z-ai": "zai",
        "zai": "zai",
    }
    return ALIASES.get(cleaned, cleaned)


def normalize_model_name(model: str | None) -> str:
    if not model:
        return "unknown"
    return model.strip().lower()


# ─── provider-usage.auth.ts ───

@dataclass
class ProviderAuthConfig:
    provider: str = ""
    api_key: str | None = None
    api_base_url: str | None = None
    organization: str | None = None
    project: str | None = None


def resolve_provider_auth(provider: str, env: dict[str, str] | None = None) -> ProviderAuthConfig:
    """Resolve auth config for a provider from environment."""
    e = env or dict(os.environ)
    p = normalize_provider_name(provider)

    KEY_MAP: dict[str, list[str]] = {
        "claude": ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY"],
        "openai": ["OPENAI_API_KEY"],
        "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        "copilot": ["GITHUB_COPILOT_TOKEN", "COPILOT_TOKEN"],
        "minimax": ["MINIMAX_API_KEY", "MINIMAX_GROUP_ID"],
        "zai": ["ZAI_API_KEY", "Z_AI_API_KEY"],
    }

    BASE_URL_MAP: dict[str, list[str]] = {
        "claude": ["ANTHROPIC_BASE_URL"],
        "openai": ["OPENAI_BASE_URL", "OPENAI_API_BASE"],
        "gemini": ["GEMINI_BASE_URL"],
        "minimax": ["MINIMAX_BASE_URL"],
        "zai": ["ZAI_BASE_URL"],
    }

    api_key = None
    for key_name in KEY_MAP.get(p, []):
        val = e.get(key_name, "").strip()
        if val:
            api_key = val
            break

    api_base = None
    for key_name in BASE_URL_MAP.get(p, []):
        val = e.get(key_name, "").strip()
        if val:
            api_base = val
            break

    return ProviderAuthConfig(
        provider=p,
        api_key=api_key,
        api_base_url=api_base,
        organization=e.get("OPENAI_ORG_ID", "").strip() or None,
        project=e.get("OPENAI_PROJECT", "").strip() or None,
    )


def has_provider_auth(provider: str, env: dict[str, str] | None = None) -> bool:
    auth = resolve_provider_auth(provider, env)
    return bool(auth.api_key)


# ─── provider-usage.fetch.shared.ts ───

def extract_usage_from_response(response: dict[str, Any]) -> ProviderUsageEntry:
    """Extract usage from a generic provider API response."""
    usage = response.get("usage", {})
    return ProviderUsageEntry(
        input_tokens=usage.get("input_tokens", usage.get("prompt_tokens", 0)),
        output_tokens=usage.get("output_tokens", usage.get("completion_tokens", 0)),
        cache_read_tokens=usage.get("cache_read_input_tokens", usage.get("cache_read_tokens", 0)),
        cache_write_tokens=usage.get("cache_creation_input_tokens", usage.get("cache_write_tokens", 0)),
        model=response.get("model", ""),
        timestamp=time.time(),
    )


# ─── provider-usage.fetch.claude.ts ───

def extract_claude_usage(response: dict[str, Any]) -> ProviderUsageEntry:
    """Extract usage from Claude/Anthropic API response."""
    usage = response.get("usage", {})
    entry = ProviderUsageEntry(
        provider="claude",
        model=response.get("model", ""),
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        cache_read_tokens=usage.get("cache_read_input_tokens", 0),
        cache_write_tokens=usage.get("cache_creation_input_tokens", 0),
        timestamp=time.time(),
    )
    entry.total_tokens = entry.input_tokens + entry.output_tokens + entry.cache_read_tokens + entry.cache_write_tokens
    return entry


# ─── provider-usage.fetch.codex.ts ───

def extract_codex_usage(response: dict[str, Any]) -> ProviderUsageEntry:
    """Extract usage from Codex/OpenAI API response."""
    usage = response.get("usage", {})
    entry = ProviderUsageEntry(
        provider="openai",
        model=response.get("model", ""),
        input_tokens=usage.get("prompt_tokens", 0),
        output_tokens=usage.get("completion_tokens", 0),
        timestamp=time.time(),
    )
    entry.total_tokens = entry.input_tokens + entry.output_tokens
    return entry


# ─── provider-usage.fetch.gemini.ts ───

def extract_gemini_usage(response: dict[str, Any]) -> ProviderUsageEntry:
    """Extract usage from Gemini/Google API response."""
    usage = response.get("usageMetadata", response.get("usage", {}))
    entry = ProviderUsageEntry(
        provider="gemini",
        model=response.get("model", response.get("modelVersion", "")),
        input_tokens=usage.get("promptTokenCount", usage.get("input_tokens", 0)),
        output_tokens=usage.get("candidatesTokenCount", usage.get("output_tokens", 0)),
        cache_read_tokens=usage.get("cachedContentTokenCount", 0),
        timestamp=time.time(),
    )
    entry.total_tokens = entry.input_tokens + entry.output_tokens + entry.cache_read_tokens
    return entry


# ─── provider-usage.fetch.copilot.ts ───

def extract_copilot_usage(response: dict[str, Any]) -> ProviderUsageEntry:
    """Extract usage from GitHub Copilot response."""
    usage = response.get("usage", {})
    entry = ProviderUsageEntry(
        provider="copilot",
        model=response.get("model", ""),
        input_tokens=usage.get("prompt_tokens", 0),
        output_tokens=usage.get("completion_tokens", 0),
        timestamp=time.time(),
    )
    entry.total_tokens = entry.input_tokens + entry.output_tokens
    return entry


# ─── provider-usage.fetch.minimax.ts ───

def extract_minimax_usage(response: dict[str, Any]) -> ProviderUsageEntry:
    """Extract usage from MiniMax API response."""
    usage = response.get("usage", {})
    base_resp = response.get("base_resp", {})
    entry = ProviderUsageEntry(
        provider="minimax",
        model=response.get("model", ""),
        input_tokens=usage.get("prompt_tokens", usage.get("total_tokens", 0)),
        output_tokens=usage.get("completion_tokens", 0),
        timestamp=time.time(),
    )
    entry.total_tokens = usage.get("total_tokens", entry.input_tokens + entry.output_tokens)
    return entry


# ─── provider-usage.fetch.zai.ts ───

def extract_zai_usage(response: dict[str, Any]) -> ProviderUsageEntry:
    """Extract usage from ZAI API response."""
    usage = response.get("usage", {})
    entry = ProviderUsageEntry(
        provider="zai",
        model=response.get("model", ""),
        input_tokens=usage.get("prompt_tokens", usage.get("input_tokens", 0)),
        output_tokens=usage.get("completion_tokens", usage.get("output_tokens", 0)),
        timestamp=time.time(),
    )
    entry.total_tokens = entry.input_tokens + entry.output_tokens
    return entry


# ─── provider-usage.fetch.ts (dispatcher) ───

_PROVIDER_EXTRACTORS: dict[str, Any] = {
    "claude": extract_claude_usage,
    "anthropic": extract_claude_usage,
    "openai": extract_codex_usage,
    "codex": extract_codex_usage,
    "gemini": extract_gemini_usage,
    "google": extract_gemini_usage,
    "copilot": extract_copilot_usage,
    "minimax": extract_minimax_usage,
    "zai": extract_zai_usage,
}


def extract_provider_usage(provider: str, response: dict[str, Any]) -> ProviderUsageEntry:
    """Extract usage from any provider's API response."""
    normalized = normalize_provider_name(provider)
    extractor = _PROVIDER_EXTRACTORS.get(normalized, extract_usage_from_response)
    entry = extractor(response)
    entry.provider = normalized
    return entry


# ─── provider-usage.format.ts ───

def format_usage_summary(summary: ProviderUsageSummary) -> str:
    """Format a provider usage summary for display."""
    parts: list[str] = []
    parts.append(f"Provider: {summary.provider}")
    parts.append(f"  Entries: {summary.entry_count}")
    parts.append(f"  Input tokens: {summary.total_input:,}")
    parts.append(f"  Output tokens: {summary.total_output:,}")
    if summary.total_cache_read > 0:
        parts.append(f"  Cache read: {summary.total_cache_read:,}")
    if summary.total_cache_write > 0:
        parts.append(f"  Cache write: {summary.total_cache_write:,}")
    parts.append(f"  Total tokens: {summary.total_tokens:,}")
    if summary.total_cost > 0:
        parts.append(f"  Cost: ${summary.total_cost:.4f}")
    if summary.models:
        parts.append(f"  Models: {', '.join(summary.models)}")
    return "\n".join(parts)


def format_token_count(count: int) -> str:
    """Format token count with thousands separators."""
    if count < 1000:
        return str(count)
    if count < 1_000_000:
        return f"{count / 1000:.1f}k"
    return f"{count / 1_000_000:.2f}M"


def format_cost(cost: float) -> str:
    """Format cost in dollars."""
    if cost < 0.01:
        return f"${cost:.4f}"
    if cost < 1.0:
        return f"${cost:.3f}"
    return f"${cost:.2f}"


# ─── provider-usage.load.ts ───

def load_usage_entries_from_file(path: str) -> list[ProviderUsageEntry]:
    """Load usage entries from a JSONL file."""
    entries: list[ProviderUsageEntry] = []
    try:
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    entries.append(ProviderUsageEntry(
                        provider=normalize_provider_name(data.get("provider")),
                        model=data.get("model", ""),
                        input_tokens=data.get("input_tokens", data.get("inputTokens", 0)),
                        output_tokens=data.get("output_tokens", data.get("outputTokens", 0)),
                        cache_read_tokens=data.get("cache_read_tokens", data.get("cacheReadTokens", 0)),
                        cache_write_tokens=data.get("cache_write_tokens", data.get("cacheWriteTokens", 0)),
                        total_tokens=data.get("total_tokens", data.get("totalTokens", 0)),
                        cost=data.get("cost"),
                        timestamp=data.get("timestamp", data.get("ts", 0)),
                    ))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return entries


def aggregate_usage_by_provider(entries: list[ProviderUsageEntry]) -> list[ProviderUsageSummary]:
    """Aggregate usage entries by provider."""
    by_provider: dict[str, ProviderUsageSummary] = {}
    for entry in entries:
        provider = entry.provider or "unknown"
        if provider not in by_provider:
            by_provider[provider] = ProviderUsageSummary(provider=provider)
        summary = by_provider[provider]
        summary.total_input += entry.input_tokens
        summary.total_output += entry.output_tokens
        summary.total_cache_read += entry.cache_read_tokens
        summary.total_cache_write += entry.cache_write_tokens
        summary.total_tokens += entry.total_tokens or (entry.input_tokens + entry.output_tokens)
        if entry.cost is not None:
            summary.total_cost += entry.cost
        summary.entry_count += 1
        if entry.model and entry.model not in summary.models:
            summary.models.append(entry.model)
    return list(by_provider.values())


# ─── provider-usage.types.ts: window/snapshot types ───

UsageProviderId = str  # "anthropic" | "github-copilot" | "google-gemini-cli" | "minimax" | "openai-codex" | "xiaomi" | "zai"

USAGE_PROVIDERS: list[str] = [
    "anthropic", "github-copilot", "google-gemini-cli",
    "minimax", "openai-codex", "xiaomi", "zai",
]

PROVIDER_LABELS: dict[str, str] = {
    "anthropic": "Claude",
    "github-copilot": "Copilot",
    "google-gemini-cli": "Gemini",
    "minimax": "MiniMax",
    "openai-codex": "Codex",
    "xiaomi": "Xiaomi",
    "zai": "z.ai",
}

IGNORED_ERRORS = {"No credentials", "No token", "No API key", "Not logged in", "No auth"}

DEFAULT_USAGE_TIMEOUT_MS = 5000


@dataclass
class UsageWindow:
    label: str = ""
    used_percent: float = 0.0
    reset_at: float | None = None  # epoch ms


@dataclass
class ProviderUsageSnapshot:
    provider: str = ""
    display_name: str = ""
    windows: list[UsageWindow] = field(default_factory=list)
    error: str | None = None
    plan: str | None = None


@dataclass
class UsageSummaryResult:
    updated_at: float = 0.0
    providers: list[ProviderUsageSnapshot] = field(default_factory=list)


def resolve_usage_provider_id(provider: str | None) -> str | None:
    if not provider:
        return None
    normalized = provider.strip().lower()
    return normalized if normalized in USAGE_PROVIDERS else None


def clamp_percent(value: float) -> float:
    if not isinstance(value, (int, float)) or not (value == value):  # NaN check
        return 0.0
    return max(0.0, min(100.0, float(value)))


# ─── provider-usage.format.ts: window-based formatting ───

def _format_reset_remaining(target_ms: float | None, now: float | None = None) -> str | None:
    """Format the time remaining until a usage window resets."""
    if not target_ms:
        return None
    base = now or (time.time() * 1000)
    diff_ms = target_ms - base
    if diff_ms <= 0:
        return "now"
    diff_mins = int(diff_ms / 60_000)
    if diff_mins < 60:
        return f"{diff_mins}m"
    hours = diff_mins // 60
    mins = diff_mins % 60
    if hours < 24:
        return f"{hours}h {mins}m" if mins > 0 else f"{hours}h"
    days = hours // 24
    if days < 7:
        return f"{days}d {hours % 24}h"
    # Longer: format as date
    import datetime
    dt = datetime.datetime.fromtimestamp(target_ms / 1000)
    return dt.strftime("%b %d")


def _format_window_short(window: UsageWindow, now: float | None = None) -> str:
    remaining = clamp_percent(100 - window.used_percent)
    reset = _format_reset_remaining(window.reset_at, now)
    reset_suffix = f" ⏱{reset}" if reset else ""
    return f"{remaining:.0f}% left ({window.label}{reset_suffix})"


def format_usage_window_summary(
    snapshot: ProviderUsageSnapshot,
    now: float | None = None,
    max_windows: int | None = None,
    include_resets: bool = False,
) -> str | None:
    """Format a provider's usage windows into a summary string."""
    if snapshot.error or not snapshot.windows:
        return None
    now_ms = now or (time.time() * 1000)
    limit = min(max_windows, len(snapshot.windows)) if max_windows and max_windows > 0 else len(snapshot.windows)
    windows = snapshot.windows[:limit]
    parts = []
    for window in windows:
        remaining = clamp_percent(100 - window.used_percent)
        reset = _format_reset_remaining(window.reset_at, now_ms) if include_resets else None
        reset_suffix = f" ⏱{reset}" if reset else ""
        parts.append(f"{window.label} {remaining:.0f}% left{reset_suffix}")
    return " · ".join(parts)


def format_usage_summary_line(
    summary: UsageSummaryResult,
    now: float | None = None,
    max_providers: int | None = None,
) -> str | None:
    """Format a one-line usage summary across providers."""
    providers = [e for e in summary.providers if e.windows and not e.error]
    if max_providers:
        providers = providers[:max_providers]
    if not providers:
        return None
    parts = []
    for entry in providers:
        best_window = max(entry.windows, key=lambda w: w.used_percent)
        parts.append(f"{entry.display_name} {_format_window_short(best_window, now)}")
    return f"📊 Usage: {' · '.join(parts)}"


def format_usage_report_lines(summary: UsageSummaryResult, now: float | None = None) -> list[str]:
    """Format a full usage report with all providers."""
    if not summary.providers:
        return ["Usage: no provider usage available."]
    lines = ["Usage:"]
    for entry in summary.providers:
        plan_suffix = f" ({entry.plan})" if entry.plan else ""
        if entry.error:
            lines.append(f"  {entry.display_name}{plan_suffix}: {entry.error}")
            continue
        if not entry.windows:
            lines.append(f"  {entry.display_name}{plan_suffix}: no data")
            continue
        lines.append(f"  {entry.display_name}{plan_suffix}")
        for window in entry.windows:
            remaining = clamp_percent(100 - window.used_percent)
            reset = _format_reset_remaining(window.reset_at, now)
            reset_suffix = f" · resets {reset}" if reset else ""
            lines.append(f"    {window.label}: {remaining:.0f}% left{reset_suffix}")
    return lines


# ─── provider-usage.load.ts ───

import asyncio
from urllib.request import Request, urlopen
from urllib.error import URLError


@dataclass
class ProviderAuth:
    provider: str = ""
    token: str = ""
    account_id: str | None = None


def resolve_provider_auths(
    providers: list[str] | None = None,
    auth: list[ProviderAuth] | None = None,
    env: dict[str, str] | None = None,
) -> list[ProviderAuth]:
    """Resolve available provider auths."""
    if auth:
        return [a for a in auth if a.token]
    target_providers = providers or USAGE_PROVIDERS
    result: list[ProviderAuth] = []
    for p in target_providers:
        pa = resolve_provider_auth(p, env)
        if pa.api_key:
            result.append(ProviderAuth(provider=p, token=pa.api_key))
    return result


async def _fetch_with_timeout(url: str, headers: dict[str, str], timeout_s: float) -> dict[str, Any]:
    """Fetch JSON from a URL with timeout."""
    loop = asyncio.get_event_loop()
    def do_fetch():
        req = Request(url, headers=headers)
        with urlopen(req, timeout=timeout_s) as resp:
            return json.loads(resp.read().decode())
    return await loop.run_in_executor(None, do_fetch)


async def load_provider_usage_summary(
    providers: list[str] | None = None,
    timeout_ms: int = DEFAULT_USAGE_TIMEOUT_MS,
    auth: list[ProviderAuth] | None = None,
    env: dict[str, str] | None = None,
    now: float | None = None,
) -> UsageSummaryResult:
    """Load usage summary from all configured providers."""
    now_ms = now or (time.time() * 1000)
    auths = resolve_provider_auths(providers, auth, env)
    if not auths:
        return UsageSummaryResult(updated_at=now_ms)

    snapshots: list[ProviderUsageSnapshot] = []
    for pa in auths:
        display_name = PROVIDER_LABELS.get(pa.provider, pa.provider)
        try:
            # Provider-specific fetching would go here
            # For now, each provider returns an empty snapshot
            snapshots.append(ProviderUsageSnapshot(
                provider=pa.provider,
                display_name=display_name,
                windows=[],
            ))
        except Exception as e:
            snapshots.append(ProviderUsageSnapshot(
                provider=pa.provider,
                display_name=display_name,
                windows=[],
                error=str(e),
            ))

    # Filter out ignored errors with no windows
    filtered = []
    for snap in snapshots:
        if snap.windows:
            filtered.append(snap)
        elif not snap.error:
            filtered.append(snap)
        elif snap.error not in IGNORED_ERRORS:
            filtered.append(snap)

    return UsageSummaryResult(updated_at=now_ms, providers=filtered)

