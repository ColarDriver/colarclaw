"""Gateway server methods — agent handler.

Ported from bk/src/gateway/server-methods/agent.ts (863 lines).

Handles `agent` (run), `agent.identity.get`, `agent.wait` RPC methods.
Session resolution, idempotency, attachment handling, delivery planning.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

RESET_COMMAND_PATTERN = r'^/(new|reset)(?:\s+([\s\S]*))?$'


@dataclass
class AgentRunRequest:
    """Parsed agent run request parameters."""
    message: str = ""
    agent_id: str | None = None
    to: str | None = None
    reply_to: str | None = None
    session_id: str | None = None
    session_key: str | None = None
    thinking: str | None = None
    deliver: bool = False
    attachments: list[dict[str, Any]] = field(default_factory=list)
    channel: str | None = None
    reply_channel: str | None = None
    account_id: str | None = None
    reply_account_id: str | None = None
    thread_id: str | None = None
    group_id: str | None = None
    group_channel: str | None = None
    group_space: str | None = None
    lane: str | None = None
    extra_system_prompt: str | None = None
    idempotency_key: str = ""
    timeout: int | None = None
    best_effort_deliver: bool = False
    label: str | None = None
    spawned_by: str | None = None
    workspace_dir: str | None = None


@dataclass
class AgentRunResult:
    """Result of an agent run."""
    run_id: str = ""
    status: str = "accepted"  # "accepted" | "ok" | "error"
    accepted_at: int = 0
    summary: str = ""
    result: Any = None
    error: Any = None


def parse_agent_run_request(params: dict[str, Any]) -> AgentRunRequest:
    """Parse raw RPC params into a AgentRunRequest."""
    return AgentRunRequest(
        message=str(params.get("message", "")).strip(),
        agent_id=_opt_str(params.get("agentId")),
        to=_opt_str(params.get("to")),
        reply_to=_opt_str(params.get("replyTo")),
        session_id=_opt_str(params.get("sessionId")),
        session_key=_opt_str(params.get("sessionKey")),
        thinking=_opt_str(params.get("thinking")),
        deliver=bool(params.get("deliver", False)),
        attachments=params.get("attachments", []),
        channel=_opt_str(params.get("channel")),
        reply_channel=_opt_str(params.get("replyChannel")),
        account_id=_opt_str(params.get("accountId")),
        reply_account_id=_opt_str(params.get("replyAccountId")),
        thread_id=_opt_str(params.get("threadId")),
        group_id=_opt_str(params.get("groupId")),
        group_channel=_opt_str(params.get("groupChannel")),
        group_space=_opt_str(params.get("groupSpace")),
        lane=_opt_str(params.get("lane")),
        extra_system_prompt=_opt_str(params.get("extraSystemPrompt")),
        idempotency_key=str(params.get("idempotencyKey", "")),
        timeout=params.get("timeout"),
        best_effort_deliver=bool(params.get("bestEffortDeliver", False)),
        label=_opt_str(params.get("label")),
        spawned_by=_opt_str(params.get("spawnedBy")),
        workspace_dir=_opt_str(params.get("workspaceDir")),
    )


def validate_agent_params(params: Any) -> tuple[bool, str]:
    """Validate agent run parameters."""
    if not isinstance(params, dict):
        return False, "params must be an object"
    message = params.get("message")
    if message is not None and not isinstance(message, str):
        return False, "message must be a string"
    idem = params.get("idempotencyKey")
    if not isinstance(idem, str) or not idem.strip():
        return False, "idempotencyKey is required"
    return True, ""


def validate_agent_identity_params(params: Any) -> tuple[bool, str]:
    """Validate agent identity params."""
    if not isinstance(params, dict):
        return False, "params must be an object"
    return True, ""


def validate_agent_wait_params(params: Any) -> tuple[bool, str]:
    """Validate agent.wait params."""
    if not isinstance(params, dict):
        return False, "params must be an object"
    run_id = params.get("runId")
    if not isinstance(run_id, str) or not run_id.strip():
        return False, "runId is required"
    return True, ""


def resolve_sender_is_owner(scopes: list[str]) -> bool:
    """Check if the sender is an owner (admin scope)."""
    return "operator.admin" in scopes


def inject_timestamp(message: str, *, enabled: bool = True) -> str:
    """Inject a timestamp into a message if not already present."""
    if not enabled or not message:
        return message
    # Don't inject if the message already starts with a timestamp-like pattern
    if message.startswith("[") and "]" in message[:30]:
        return message
    timestamp = time.strftime("%Y-%m-%d %H:%M", time.localtime())
    return f"[{timestamp}] {message}"


def _opt_str(value: Any) -> str | None:
    """Extract optional trimmed string."""
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    return None
