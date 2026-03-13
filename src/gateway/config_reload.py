"""Gateway config reload — ported from bk/src/gateway/config-reload.ts,
config-reload-plan.ts, server-reload-handlers.ts, server-runtime-config.ts.

Hot-reload of gateway configuration without restart: plan computation,
diff detection, handler re-initialization, and model validation.
"""
from __future__ import annotations

import asyncio
import copy
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ─── config-reload-plan.ts — Reload plan computation ───

@dataclass
class ConfigChange:
    """A single configuration change."""
    path: str = ""
    old_value: Any = None
    new_value: Any = None
    change_type: str = ""  # "added" | "removed" | "modified"


@dataclass
class ConfigReloadPlan:
    """Plan describing what needs to happen when config changes."""
    changes: list[ConfigChange] = field(default_factory=list)
    needs_channel_restart: set[str] = field(default_factory=set)
    needs_auth_reload: bool = False
    needs_hooks_reload: bool = False
    needs_cron_reload: bool = False
    needs_model_reload: bool = False
    needs_tls_reload: bool = False
    needs_full_restart: bool = False
    description: str = ""


def compute_reload_plan(
    old_cfg: dict[str, Any],
    new_cfg: dict[str, Any],
) -> ConfigReloadPlan:
    """Compute what needs to change when configuration is updated.

    Performs a deep diff of old and new config, categorizing changes
    into actionable reload steps.
    """
    plan = ConfigReloadPlan()
    changes = _deep_diff(old_cfg, new_cfg, "")

    for change in changes:
        plan.changes.append(change)
        path = change.path

        # Determine what needs reloading based on path
        if path.startswith("gateway.auth"):
            plan.needs_auth_reload = True
        elif path.startswith("gateway.hooks"):
            plan.needs_hooks_reload = True
        elif path.startswith("gateway.tls"):
            plan.needs_tls_reload = True
        elif path.startswith("gateway.bind") or path.startswith("gateway.port"):
            plan.needs_full_restart = True
        elif path.startswith("cron"):
            plan.needs_cron_reload = True
        elif path.startswith("agent.model") or path.startswith("agent.provider"):
            plan.needs_model_reload = True
        elif _is_channel_path(path):
            channel = _extract_channel_from_path(path)
            if channel:
                plan.needs_channel_restart.add(channel)

    parts = []
    if plan.changes:
        parts.append(f"{len(plan.changes)} config change(s)")
    if plan.needs_channel_restart:
        parts.append(f"channel restart: {', '.join(sorted(plan.needs_channel_restart))}")
    if plan.needs_auth_reload:
        parts.append("auth reload")
    if plan.needs_hooks_reload:
        parts.append("hooks reload")
    if plan.needs_cron_reload:
        parts.append("cron reload")
    if plan.needs_model_reload:
        parts.append("model reload")
    if plan.needs_full_restart:
        parts.append("FULL RESTART REQUIRED")
    plan.description = "; ".join(parts) if parts else "no changes"

    return plan


def _is_channel_path(path: str) -> bool:
    """Check if a config path relates to a channel."""
    channel_prefixes = [
        "telegram", "discord", "slack", "signal", "imessage",
        "web", "whatsapp", "matrix", "msteams", "zalo",
    ]
    return any(path.startswith(prefix) for prefix in channel_prefixes)


def _extract_channel_from_path(path: str) -> str | None:
    """Extract channel name from a config path."""
    parts = path.split(".")
    return parts[0] if parts else None


def _deep_diff(
    old: Any,
    new: Any,
    prefix: str,
) -> list[ConfigChange]:
    """Deep-diff two config values, returning a list of changes."""
    changes: list[ConfigChange] = []

    if isinstance(old, dict) and isinstance(new, dict):
        all_keys = set(old.keys()) | set(new.keys())
        for key in sorted(all_keys):
            child_path = f"{prefix}.{key}" if prefix else key
            if key not in old:
                changes.append(ConfigChange(
                    path=child_path,
                    new_value=new[key],
                    change_type="added",
                ))
            elif key not in new:
                changes.append(ConfigChange(
                    path=child_path,
                    old_value=old[key],
                    change_type="removed",
                ))
            else:
                changes.extend(_deep_diff(old[key], new[key], child_path))
    elif old != new:
        changes.append(ConfigChange(
            path=prefix,
            old_value=old,
            new_value=new,
            change_type="modified",
        ))

    return changes


# ─── config-reload.ts — Reload execution ───

class ConfigReloader:
    """Watches for config changes and applies reload plans.

    Supports file-system watching and manual reload triggers.
    """

    def __init__(
        self,
        *,
        config_path: str = "",
        load_config_fn: Callable[[], dict[str, Any]] | None = None,
        on_reload: Callable[[ConfigReloadPlan, dict[str, Any]], Any] | None = None,
        interval_ms: int = 5_000,
    ) -> None:
        self._config_path = config_path
        self._load_config = load_config_fn
        self._on_reload = on_reload
        self._interval_ms = interval_ms
        self._current_config: dict[str, Any] = {}
        self._watch_task: asyncio.Task | None = None
        self._stopped = False

    async def start(self, initial_config: dict[str, Any] | None = None) -> None:
        """Start watching for config changes."""
        if initial_config:
            self._current_config = copy.deepcopy(initial_config)
        self._watch_task = asyncio.create_task(self._watch_loop())

    async def stop(self) -> None:
        """Stop watching."""
        self._stopped = True
        if self._watch_task:
            self._watch_task.cancel()
            self._watch_task = None

    async def trigger_reload(self) -> ConfigReloadPlan:
        """Manually trigger a config reload."""
        if not self._load_config:
            return ConfigReloadPlan(description="no config loader")

        try:
            new_config = self._load_config()
        except Exception as e:
            logger.error(f"config reload failed: {e}")
            return ConfigReloadPlan(description=f"load error: {e}")

        plan = compute_reload_plan(self._current_config, new_config)

        if plan.changes and self._on_reload:
            try:
                result = self._on_reload(plan, new_config)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"config reload handler error: {e}")
                plan.description += f"; handler error: {e}"

        self._current_config = copy.deepcopy(new_config)
        return plan

    async def _watch_loop(self) -> None:
        """Periodically check for config changes."""
        while not self._stopped:
            try:
                await asyncio.sleep(self._interval_ms / 1000)
                if self._stopped:
                    break
                await self.trigger_reload()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"config watch error: {e}")


# ─── server-runtime-config.ts — Runtime config access ───

@dataclass
class GatewayRuntimeConfig:
    """Runtime-accessible gateway configuration."""
    bind_host: str = "127.0.0.1"
    port: int = 18789
    tls_enabled: bool = False
    auth_mode: str = "none"
    control_ui_enabled: bool = False
    control_ui_base_path: str = "/_"
    openai_compat_enabled: bool = False
    open_responses_enabled: bool = False
    canvas_host_enabled: bool = False
    model_provider: str = ""
    model: str = ""
    hooks_enabled: bool = False
    cron_enabled: bool = False
    nix_mode: bool = False
    config_path: str = ""


def resolve_runtime_config(cfg: dict[str, Any]) -> GatewayRuntimeConfig:
    """Resolve runtime config from raw config dict."""
    gw = cfg.get("gateway", {}) or {}
    auth = gw.get("auth", {}) or {}
    control_ui = gw.get("controlUi", {}) or {}
    hooks = gw.get("hooks", {}) or {}
    cron = cfg.get("cron", {}) or {}
    agent = cfg.get("agent", {}) or {}

    return GatewayRuntimeConfig(
        bind_host=gw.get("bind", "127.0.0.1"),
        port=int(gw.get("port", 18789)),
        tls_enabled=bool(gw.get("tls", {}).get("enabled", False)),
        auth_mode=auth.get("mode", "none"),
        control_ui_enabled=bool(control_ui.get("enabled", False)),
        control_ui_base_path=control_ui.get("basePath", "/_"),
        openai_compat_enabled=bool(gw.get("httpChatCompletions", {}).get("enabled", False)),
        open_responses_enabled=bool(gw.get("httpResponses", {}).get("enabled", False)),
        canvas_host_enabled=bool(gw.get("canvasHost", {}).get("enabled", False)),
        model_provider=agent.get("modelProvider", ""),
        model=agent.get("model", ""),
        hooks_enabled=bool(hooks.get("enabled", False)),
        cron_enabled=bool(cron.get("enabled", False)),
    )
