"""Gateway exec approval manager — ported from bk/src/gateway/exec-approval-manager.ts,
server-methods/exec-approval.ts, server-methods/exec-approvals.ts.

Tracks pending exec approvals (tool calls, system commands) and resolves them
when operators approve/deny.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ─── Types ───

@dataclass
class ExecApprovalRequest:
    """A pending exec approval request."""
    id: str = ""
    node_id: str = ""
    session_key: str = ""
    command: str = ""
    args: list[str] = field(default_factory=list)
    cwd: str = ""
    tool_name: str | None = None
    tool_call_id: str | None = None
    run_id: str | None = None
    conn_id: str = ""
    requested_at_ms: int = 0
    timeout_ms: int = 300_000  # 5 minutes
    auto_approve: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecApprovalResolution:
    """Resolution of an exec approval."""
    id: str = ""
    approved: bool = False
    resolved_by: str = ""
    resolved_at_ms: int = 0
    reason: str = ""


@dataclass
class ExecApprovalSnapshot:
    """Snapshot of all pending approvals."""
    pending: list[ExecApprovalRequest] = field(default_factory=list)
    total_resolved: int = 0
    total_expired: int = 0


# ─── Exec approval manager ───

class ExecApprovalManager:
    """Manages pending exec approvals with timeout and resolution.

    When a tool or system command needs operator approval, it creates
    an approval request. Operators approve/deny via the control UI
    or CLI. Expired requests are auto-denied.
    """

    def __init__(
        self,
        *,
        on_approval: Callable[[str, ExecApprovalResolution], None] | None = None,
        broadcast_fn: Callable[[str, Any], None] | None = None,
    ) -> None:
        self._pending: dict[str, ExecApprovalRequest] = {}
        self._futures: dict[str, asyncio.Future] = {}
        self._on_approval = on_approval
        self._broadcast = broadcast_fn
        self._total_resolved = 0
        self._total_expired = 0
        self._cleanup_task: asyncio.Task | None = None

    def start(self) -> None:
        """Start the cleanup timer for expired approvals."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    def stop(self) -> None:
        """Stop the cleanup timer and deny all pending."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None
        # Deny all pending
        for req_id in list(self._pending.keys()):
            self._resolve(req_id, approved=False, resolved_by="system", reason="gateway stopping")

    async def request_approval(
        self,
        *,
        node_id: str = "",
        session_key: str = "",
        command: str = "",
        args: list[str] | None = None,
        cwd: str = "",
        tool_name: str | None = None,
        tool_call_id: str | None = None,
        run_id: str | None = None,
        conn_id: str = "",
        timeout_ms: int = 300_000,
        metadata: dict[str, Any] | None = None,
    ) -> ExecApprovalResolution:
        """Create an approval request and wait for resolution.

        Raises TimeoutError if not resolved within timeout_ms.
        """
        req_id = str(uuid.uuid4())
        request = ExecApprovalRequest(
            id=req_id,
            node_id=node_id,
            session_key=session_key,
            command=command,
            args=args or [],
            cwd=cwd,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            run_id=run_id,
            conn_id=conn_id,
            requested_at_ms=int(time.time() * 1000),
            timeout_ms=timeout_ms,
            metadata=metadata or {},
        )

        self._pending[req_id] = request

        loop = asyncio.get_event_loop()
        future: asyncio.Future[ExecApprovalResolution] = loop.create_future()
        self._futures[req_id] = future

        # Broadcast request event
        if self._broadcast:
            self._broadcast("exec.approval.requested", {
                "id": req_id,
                "nodeId": node_id,
                "sessionKey": session_key,
                "command": command,
                "args": args or [],
                "cwd": cwd,
                "toolName": tool_name,
                "toolCallId": tool_call_id,
                "runId": run_id,
                "requestedAtMs": request.requested_at_ms,
            })

        try:
            return await asyncio.wait_for(future, timeout=timeout_ms / 1000)
        except asyncio.TimeoutError:
            self._total_expired += 1
            self._pending.pop(req_id, None)
            self._futures.pop(req_id, None)
            return ExecApprovalResolution(
                id=req_id,
                approved=False,
                resolved_by="system",
                resolved_at_ms=int(time.time() * 1000),
                reason="timeout",
            )

    def resolve(
        self,
        request_id: str,
        *,
        approved: bool,
        resolved_by: str = "operator",
        reason: str = "",
    ) -> bool:
        """Resolve a pending approval. Returns True if found and resolved."""
        return self._resolve(request_id, approved=approved,
                             resolved_by=resolved_by, reason=reason)

    def _resolve(
        self,
        request_id: str,
        *,
        approved: bool,
        resolved_by: str,
        reason: str = "",
    ) -> bool:
        request = self._pending.pop(request_id, None)
        future = self._futures.pop(request_id, None)
        if not request or not future:
            return False

        resolution = ExecApprovalResolution(
            id=request_id,
            approved=approved,
            resolved_by=resolved_by,
            resolved_at_ms=int(time.time() * 1000),
            reason=reason,
        )

        self._total_resolved += 1

        if not future.done():
            future.set_result(resolution)

        if self._on_approval:
            self._on_approval(request_id, resolution)

        if self._broadcast:
            self._broadcast("exec.approval.resolved", {
                "id": request_id,
                "approved": approved,
                "resolvedBy": resolved_by,
                "reason": reason,
            })

        return True

    def get_pending(self) -> list[ExecApprovalRequest]:
        """List all pending approvals."""
        return list(self._pending.values())

    def get_snapshot(self) -> ExecApprovalSnapshot:
        """Get a snapshot of approval state."""
        return ExecApprovalSnapshot(
            pending=list(self._pending.values()),
            total_resolved=self._total_resolved,
            total_expired=self._total_expired,
        )

    def get_node_pending(self, node_id: str) -> list[ExecApprovalRequest]:
        """Get pending approvals for a specific node."""
        return [r for r in self._pending.values() if r.node_id == node_id]

    async def _cleanup_loop(self) -> None:
        """Periodically expire timed-out approval requests."""
        while True:
            try:
                await asyncio.sleep(30)
                now_ms = int(time.time() * 1000)
                expired = [
                    req_id for req_id, req in self._pending.items()
                    if now_ms - req.requested_at_ms > req.timeout_ms
                ]
                for req_id in expired:
                    self._resolve(req_id, approved=False, resolved_by="system", reason="expired")
                    self._total_expired += 1
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"exec approval cleanup error: {e}")
