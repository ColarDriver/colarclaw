"""ACP policy — ported from bk/src/acp/policy.ts.

Policy checks for ACP enablement, dispatch, and agent allowlists.
"""
from __future__ import annotations

from typing import Any, Literal

AcpDispatchPolicyState = Literal["enabled", "acp_disabled", "dispatch_disabled"]

ACP_DISABLED_MESSAGE = "ACP is disabled by policy (`acp.enabled=false`)."
ACP_DISPATCH_DISABLED_MESSAGE = "ACP dispatch is disabled by policy (`acp.dispatch.enabled=false`)."


def is_acp_enabled_by_policy(cfg: Any) -> bool:
    acp = getattr(cfg, "acp", None)
    if not acp:
        return True
    return getattr(acp, "enabled", None) is not False


def resolve_acp_dispatch_policy_state(cfg: Any) -> AcpDispatchPolicyState:
    if not is_acp_enabled_by_policy(cfg):
        return "acp_disabled"
    acp = getattr(cfg, "acp", None)
    dispatch = getattr(acp, "dispatch", None) if acp else None
    if dispatch and getattr(dispatch, "enabled", None) is False:
        return "dispatch_disabled"
    return "enabled"


def is_acp_dispatch_enabled_by_policy(cfg: Any) -> bool:
    return resolve_acp_dispatch_policy_state(cfg) == "enabled"


def resolve_acp_dispatch_policy_message(cfg: Any) -> str | None:
    state = resolve_acp_dispatch_policy_state(cfg)
    if state == "acp_disabled":
        return ACP_DISABLED_MESSAGE
    if state == "dispatch_disabled":
        return ACP_DISPATCH_DISABLED_MESSAGE
    return None


class AcpRuntimeError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def resolve_acp_dispatch_policy_error(cfg: Any) -> AcpRuntimeError | None:
    message = resolve_acp_dispatch_policy_message(cfg)
    return AcpRuntimeError("ACP_DISPATCH_DISABLED", message) if message else None


def _normalize_agent_id(value: str) -> str:
    return value.strip().lower()


def is_acp_agent_allowed_by_policy(cfg: Any, agent_id: str) -> bool:
    acp = getattr(cfg, "acp", None)
    allowed_agents = getattr(acp, "allowed_agents", None) or getattr(acp, "allowedAgents", None) or []
    allowed = [_normalize_agent_id(e) for e in allowed_agents if _normalize_agent_id(e)]
    if not allowed:
        return True
    return _normalize_agent_id(agent_id) in allowed


def resolve_acp_agent_policy_error(cfg: Any, agent_id: str) -> AcpRuntimeError | None:
    if is_acp_agent_allowed_by_policy(cfg, agent_id):
        return None
    return AcpRuntimeError(
        "ACP_SESSION_INIT_FAILED",
        f'ACP agent "{_normalize_agent_id(agent_id)}" is not allowed by policy.',
    )
