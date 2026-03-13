"""Commands — deep handlers: configure wizard, models probe, sessions, delivery.

Deep supplemental port for bk/src/commands/ ~40k行 remaining coverage.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── Configure wizard ───

@dataclass
class ConfigureStep:
    title: str = ""
    key: str = ""
    type: str = "text"  # "text" | "select" | "bool" | "secret"
    current_value: Any = None
    options: list[dict[str, str]] = field(default_factory=list)
    validate: Any = None


CONFIGURE_SECTIONS = {
    "models": [
        ConfigureStep(title="Default model", key="agents.defaults.model",
                      type="select", options=[
                          {"label": "Claude Sonnet 4", "value": "claude-sonnet-4-20250514"},
                          {"label": "GPT-4o", "value": "gpt-4o"},
                          {"label": "Gemini 2.0 Flash", "value": "gemini-2.0-flash"},
                          {"label": "Grok-3", "value": "grok-3"},
                      ]),
        ConfigureStep(title="Thinking mode", key="agents.defaults.thinking",
                      type="select", options=[
                          {"label": "Off", "value": "off"},
                          {"label": "Low", "value": "low"},
                          {"label": "Medium", "value": "medium"},
                          {"label": "High", "value": "high"},
                      ]),
        ConfigureStep(title="Max tokens", key="agents.defaults.maxTokens", type="text"),
    ],
    "gateway": [
        ConfigureStep(title="Gateway mode", key="gateway.mode",
                      type="select", options=[
                          {"label": "Local", "value": "local"},
                          {"label": "Remote", "value": "remote"},
                      ]),
        ConfigureStep(title="Port", key="gateway.port", type="text"),
        ConfigureStep(title="Bind", key="gateway.bind",
                      type="select", options=[
                          {"label": "Loopback (127.0.0.1)", "value": "loopback"},
                          {"label": "All interfaces", "value": "0.0.0.0"},
                          {"label": "Tailscale", "value": "tailscale"},
                      ]),
    ],
    "sessions": [
        ConfigureStep(title="Max session age (hours)", key="sessions.maxAgeHours", type="text"),
        ConfigureStep(title="Auto-cleanup", key="sessions.autoCleanup", type="bool"),
        ConfigureStep(title="Compaction enabled", key="sessions.compaction.enabled", type="bool"),
    ],
    "logging": [
        ConfigureStep(title="Log level", key="logging.level",
                      type="select", options=[
                          {"label": "Debug", "value": "debug"},
                          {"label": "Info", "value": "info"},
                          {"label": "Warning", "value": "warn"},
                          {"label": "Error", "value": "error"},
                      ]),
        ConfigureStep(title="Log to file", key="logging.file", type="bool"),
        ConfigureStep(title="Structured (JSON)", key="logging.structured", type="bool"),
    ],
}


async def run_configure_wizard(
    config: dict[str, Any],
    *,
    section: str = "",
) -> dict[str, Any]:
    """Interactive configuration wizard."""
    changes: dict[str, Any] = {}
    sections = {section: CONFIGURE_SECTIONS[section]} if section and section in CONFIGURE_SECTIONS else CONFIGURE_SECTIONS
    
    for sec_name, steps in sections.items():
        print(f"\n  ── {sec_name.title()} ──")
        for step in steps:
            current = _get_nested_value(config, step.key)
            if step.type == "select" and step.options:
                print(f"\n  {step.title}")
                for i, opt in enumerate(step.options):
                    marker = "●" if opt["value"] == str(current) else "○"
                    print(f"    {marker} {i+1}. {opt['label']}")
                try:
                    choice = input(f"  Choice [{current or 'none'}]: ").strip()
                    if choice:
                        idx = int(choice) - 1
                        if 0 <= idx < len(step.options):
                            changes[step.key] = step.options[idx]["value"]
                except (ValueError, EOFError):
                    pass
            elif step.type == "bool":
                try:
                    hint = "Y/n" if current else "y/N"
                    val = input(f"  {step.title} [{hint}]: ").strip().lower()
                    if val in ("y", "yes", "true"):
                        changes[step.key] = True
                    elif val in ("n", "no", "false"):
                        changes[step.key] = False
                except (EOFError, KeyboardInterrupt):
                    pass
            elif step.type == "secret":
                try:
                    import getpass
                    val = getpass.getpass(f"  {step.title}: ")
                    if val:
                        changes[step.key] = val
                except (EOFError, KeyboardInterrupt):
                    pass
            else:
                try:
                    val = input(f"  {step.title} [{current or ''}]: ").strip()
                    if val:
                        changes[step.key] = val
                except (EOFError, KeyboardInterrupt):
                    pass
    
    return changes


def _get_nested_value(d: dict[str, Any], path: str) -> Any:
    parts = path.split(".")
    current: Any = d
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def apply_config_changes(config: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    """Apply dotted-path changes to config."""
    import copy
    result = copy.deepcopy(config)
    for path, value in changes.items():
        parts = path.split(".")
        target = result
        for part in parts[:-1]:
            if part not in target or not isinstance(target[part], dict):
                target[part] = {}
            target = target[part]
        target[parts[-1]] = value
    return result


# ─── Models probe ───

@dataclass
class ModelInfo:
    id: str = ""
    name: str = ""
    provider: str = ""
    context_window: int = 0
    max_output_tokens: int = 0
    supports_vision: bool = False
    supports_tools: bool = False
    supports_thinking: bool = False
    cost_per_1m_input: float = 0
    cost_per_1m_output: float = 0


MODEL_CATALOG: list[ModelInfo] = [
    ModelInfo(id="claude-sonnet-4-20250514", name="Claude Sonnet 4", provider="anthropic",
             context_window=200_000, max_output_tokens=16_384,
             supports_vision=True, supports_tools=True, supports_thinking=True,
             cost_per_1m_input=3.0, cost_per_1m_output=15.0),
    ModelInfo(id="claude-3-5-haiku-20241022", name="Claude 3.5 Haiku", provider="anthropic",
             context_window=200_000, max_output_tokens=8_192,
             supports_vision=True, supports_tools=True,
             cost_per_1m_input=0.8, cost_per_1m_output=4.0),
    ModelInfo(id="gpt-4o", name="GPT-4o", provider="openai",
             context_window=128_000, max_output_tokens=16_384,
             supports_vision=True, supports_tools=True,
             cost_per_1m_input=2.5, cost_per_1m_output=10.0),
    ModelInfo(id="gpt-4o-mini", name="GPT-4o Mini", provider="openai",
             context_window=128_000, max_output_tokens=16_384,
             supports_vision=True, supports_tools=True,
             cost_per_1m_input=0.15, cost_per_1m_output=0.6),
    ModelInfo(id="gemini-2.0-flash", name="Gemini 2.0 Flash", provider="google",
             context_window=1_048_576, max_output_tokens=8_192,
             supports_vision=True, supports_tools=True,
             cost_per_1m_input=0.075, cost_per_1m_output=0.3),
    ModelInfo(id="grok-3", name="Grok-3", provider="xai",
             context_window=131_072, max_output_tokens=16_384,
             supports_tools=True, supports_thinking=True,
             cost_per_1m_input=3.0, cost_per_1m_output=15.0),
]


def list_available_models(*, provider: str = "") -> list[ModelInfo]:
    if provider:
        return [m for m in MODEL_CATALOG if m.provider == provider]
    return list(MODEL_CATALOG)


def get_model_info(model_id: str) -> ModelInfo | None:
    return next((m for m in MODEL_CATALOG if m.id == model_id), None)


# ─── Sessions table ───

@dataclass
class SessionSummary:
    key: str = ""
    agent_id: str = ""
    channel: str = ""
    message_count: int = 0
    token_count: int = 0
    created_at: str = ""
    last_activity: str = ""
    size_bytes: int = 0


async def list_session_summaries(sessions_dir: str) -> list[SessionSummary]:
    """List session summaries from session storage."""
    summaries = []
    if not os.path.isdir(sessions_dir):
        return summaries
    
    for entry in sorted(os.listdir(sessions_dir)):
        session_dir = os.path.join(sessions_dir, entry)
        if not os.path.isdir(session_dir):
            continue
        meta_path = os.path.join(session_dir, "meta.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path) as f:
                    meta = json.load(f)
                total_size = sum(
                    os.path.getsize(os.path.join(session_dir, f))
                    for f in os.listdir(session_dir)
                    if os.path.isfile(os.path.join(session_dir, f))
                )
                summaries.append(SessionSummary(
                    key=entry,
                    agent_id=meta.get("agentId", ""),
                    channel=meta.get("channel", ""),
                    message_count=meta.get("messageCount", 0),
                    token_count=meta.get("tokenCount", 0),
                    created_at=meta.get("createdAt", ""),
                    last_activity=meta.get("lastActivity", ""),
                    size_bytes=total_size,
                ))
            except Exception:
                summaries.append(SessionSummary(key=entry))
    
    return summaries


async def cleanup_old_sessions(
    sessions_dir: str,
    *,
    max_age_hours: int = 168,
    dry_run: bool = False,
) -> list[str]:
    """Cleanup sessions older than max_age_hours."""
    import shutil
    cutoff_ms = int(time.time() * 1000) - max_age_hours * 3600 * 1000
    removed = []
    
    if not os.path.isdir(sessions_dir):
        return removed
    
    for entry in os.listdir(sessions_dir):
        session_dir = os.path.join(sessions_dir, entry)
        if not os.path.isdir(session_dir):
            continue
        meta_path = os.path.join(session_dir, "meta.json")
        last_activity_ms = 0
        if os.path.exists(meta_path):
            try:
                with open(meta_path) as f:
                    meta = json.load(f)
                last_activity_ms = meta.get("lastActivityMs", 0)
            except Exception:
                pass
        if not last_activity_ms:
            last_activity_ms = int(os.path.getmtime(session_dir) * 1000)
        
        if last_activity_ms < cutoff_ms:
            if not dry_run:
                shutil.rmtree(session_dir, ignore_errors=True)
            removed.append(entry)
    
    return removed
