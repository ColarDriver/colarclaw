"""Gateway config and hooks — ported from bk/src/gateway/ config/hooks files.

Config reload planning, execution, hooks mapping, and gateway config prompts.
Consolidates: config-reload.ts, config-reload-plan.ts, hooks.ts, hooks-mapping.ts,
  gateway-config-prompts.shared.ts, exec-approval-manager.ts.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ─── config-reload-plan.ts ───

@dataclass
class ConfigReloadPlanItem:
    action: str = ""  # "restart_channel" | "reload_agent" | "update_hooks" | "noop"
    target: str = ""  # channel name, agent id, etc.
    reason: str = ""


def build_config_reload_plan(
    old_cfg: dict[str, Any],
    new_cfg: dict[str, Any],
) -> list[ConfigReloadPlanItem]:
    """Compute what needs to change when config is reloaded."""
    plan: list[ConfigReloadPlanItem] = []

    # Check channels
    old_channels = set((old_cfg.get("channels") or {}).keys())
    new_channels = set((new_cfg.get("channels") or {}).keys())
    for ch in new_channels - old_channels:
        plan.append(ConfigReloadPlanItem("restart_channel", ch, "new channel"))
    for ch in old_channels - new_channels:
        plan.append(ConfigReloadPlanItem("restart_channel", ch, "removed channel"))
    for ch in old_channels & new_channels:
        if (old_cfg.get("channels") or {}).get(ch) != (new_cfg.get("channels") or {}).get(ch):
            plan.append(ConfigReloadPlanItem("restart_channel", ch, "config changed"))

    # Check agents
    old_agents = old_cfg.get("agents", {}).get("list", [])
    new_agents = new_cfg.get("agents", {}).get("list", [])
    old_ids = {a.get("id") for a in old_agents if isinstance(a, dict)}
    new_ids = {a.get("id") for a in new_agents if isinstance(a, dict)}
    for aid in new_ids - old_ids:
        plan.append(ConfigReloadPlanItem("reload_agent", aid or "", "new agent"))
    for aid in old_ids - new_ids:
        plan.append(ConfigReloadPlanItem("reload_agent", aid or "", "removed agent"))

    return plan


# ─── config-reload.ts ───

@dataclass
class ConfigReloadResult:
    success: bool = False
    plan: list[ConfigReloadPlanItem] = field(default_factory=list)
    error: str | None = None
    duration_ms: int = 0


# ─── hooks-mapping.ts ───

HOOK_EVENTS = [
    "on_message_received",
    "on_message_sent",
    "on_agent_run_start",
    "on_agent_run_end",
    "on_session_created",
    "on_session_ended",
    "on_config_reload",
    "on_channel_connected",
    "on_channel_disconnected",
]


@dataclass
class HookMapping:
    event: str = ""
    handler: str = ""
    priority: int = 0
    enabled: bool = True


def resolve_hook_mappings(cfg: dict[str, Any]) -> list[HookMapping]:
    """Resolve hook mappings from config."""
    hooks_cfg = cfg.get("hooks", {})
    if not isinstance(hooks_cfg, dict):
        return []
    mappings = []
    for event in HOOK_EVENTS:
        handlers = hooks_cfg.get(event, [])
        if isinstance(handlers, list):
            for i, handler in enumerate(handlers):
                if isinstance(handler, str) and handler.strip():
                    mappings.append(HookMapping(
                        event=event,
                        handler=handler.strip(),
                        priority=i,
                    ))
                elif isinstance(handler, dict):
                    mappings.append(HookMapping(
                        event=event,
                        handler=str(handler.get("handler", "")),
                        priority=handler.get("priority", i),
                        enabled=handler.get("enabled", True),
                    ))
    return mappings


# ─── exec-approval-manager.ts ───

@dataclass
class ExecApprovalRequest:
    request_id: str = ""
    session_key: str = ""
    command: str = ""
    created_at_ms: int = 0
    status: str = "pending"  # "pending" | "approved" | "denied" | "expired"
    decided_at_ms: int = 0


class ExecApprovalManager:
    """Manage exec approval requests."""

    def __init__(self, ttl_ms: int = 300_000) -> None:
        self._requests: dict[str, ExecApprovalRequest] = {}
        self._ttl_ms = ttl_ms

    def submit(self, request_id: str, session_key: str, command: str) -> ExecApprovalRequest:
        req = ExecApprovalRequest(
            request_id=request_id,
            session_key=session_key,
            command=command,
            created_at_ms=int(time.time() * 1000),
        )
        self._requests[request_id] = req
        return req

    def decide(self, request_id: str, approved: bool) -> ExecApprovalRequest | None:
        req = self._requests.get(request_id)
        if not req or req.status != "pending":
            return None
        req.status = "approved" if approved else "denied"
        req.decided_at_ms = int(time.time() * 1000)
        return req

    def get(self, request_id: str) -> ExecApprovalRequest | None:
        req = self._requests.get(request_id)
        if req and req.status == "pending":
            now = int(time.time() * 1000)
            if now - req.created_at_ms > self._ttl_ms:
                req.status = "expired"
        return req

    def list_pending(self, session_key: str | None = None) -> list[ExecApprovalRequest]:
        now = int(time.time() * 1000)
        results = []
        for req in self._requests.values():
            if req.status == "pending":
                if now - req.created_at_ms > self._ttl_ms:
                    req.status = "expired"
                    continue
                if session_key and req.session_key != session_key:
                    continue
                results.append(req)
        return results

    def cleanup(self) -> int:
        now = int(time.time() * 1000)
        expired = [
            rid for rid, req in self._requests.items()
            if req.status != "pending" or (now - req.created_at_ms > self._ttl_ms * 2)
        ]
        for rid in expired:
            del self._requests[rid]
        return len(expired)
