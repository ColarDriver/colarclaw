"""Infra channel_extended — ported from bk/src/infra/channel-activity.ts,
channel-summary.ts, channels-status-issues.ts, node-commands.ts,
windows-task-restart.ts.

Channel activity tracking, channel summary building, status issue
collection, node commands, Windows task restart.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

logger = logging.getLogger("infra.channel_extended")


# ─── channel-activity.ts ───

ChannelDirection = Literal["inbound", "outbound"]


@dataclass
class ActivityEntry:
    inbound_at: float | None = None
    outbound_at: float | None = None


_activity: dict[str, ActivityEntry] = {}


def _activity_key(channel: str, account_id: str | None = None) -> str:
    return f"{channel}:{(account_id or '').strip() or 'default'}"


def record_channel_activity(
    channel: str,
    direction: str,
    account_id: str | None = None,
    at: float | None = None,
) -> None:
    """Record inbound/outbound activity for a channel."""
    key = _activity_key(channel, account_id)
    ts = at if at is not None else time.time()
    if key not in _activity:
        _activity[key] = ActivityEntry()
    entry = _activity[key]
    if direction == "inbound":
        entry.inbound_at = ts
    elif direction == "outbound":
        entry.outbound_at = ts


def get_channel_activity(
    channel: str, account_id: str | None = None,
) -> ActivityEntry:
    key = _activity_key(channel, account_id)
    return _activity.get(key, ActivityEntry())


def reset_channel_activity_for_test() -> None:
    _activity.clear()


# ─── channel-summary.ts ───

@dataclass
class ChannelSummaryEntry:
    channel: str = ""
    label: str = ""
    status: str = ""  # "linked" | "configured" | "disabled" | "not linked" | "not configured"
    accounts: list[dict[str, Any]] = field(default_factory=list)
    details: list[str] = field(default_factory=list)


def build_channel_summary(
    channels: list[dict[str, Any]],
    colorize: bool = False,
    include_allow_from: bool = False,
) -> list[str]:
    """Build channel summary lines for display."""
    lines: list[str] = []
    for ch in channels:
        label = ch.get("label", ch.get("id", "unknown"))
        enabled = ch.get("enabled", False)
        configured = ch.get("configured", False)
        linked = ch.get("linked")

        if not enabled:
            status = "disabled"
        elif linked is not None:
            status = "linked" if linked else "not linked"
        elif configured:
            status = "configured"
        else:
            status = "not configured"

        line = f"{label}: {status}"
        # Add auth age if available
        auth_age_ms = ch.get("authAgeMs")
        if auth_age_ms is not None and auth_age_ms >= 0:
            from ..util.formatting import format_relative_time
            line += f" auth {format_relative_time(auth_age_ms / 1000)}"

        lines.append(line)

        # Account details
        accounts = ch.get("accounts", [])
        for acct in accounts:
            acct_id = acct.get("accountId", "default")
            details: list[str] = []
            if acct.get("enabled") is False:
                details.append("disabled")
            if acct.get("dmPolicy"):
                details.append(f"dm:{acct['dmPolicy']}")
            if acct.get("tokenSource") and acct["tokenSource"] != "none":
                details.append(f"token:{acct['tokenSource']}")
            detail_str = f" ({', '.join(details)})" if details else ""
            lines.append(f"  - {acct_id}{detail_str}")

    return lines


# ─── channels-status-issues.ts ───

@dataclass
class ChannelStatusIssue:
    channel: str = ""
    severity: str = "warn"  # "info" | "warn" | "error"
    message: str = ""
    fix_hint: str | None = None


def collect_channel_status_issues(
    channel_accounts: dict[str, list[dict[str, Any]]],
    issue_collectors: dict[str, Callable[[list[dict[str, Any]]], list[ChannelStatusIssue]]] | None = None,
) -> list[ChannelStatusIssue]:
    """Collect status issues from all channel plugins."""
    issues: list[ChannelStatusIssue] = []
    if not issue_collectors:
        return issues
    for channel_id, accounts in channel_accounts.items():
        collector = issue_collectors.get(channel_id)
        if collector:
            try:
                issues.extend(collector(accounts))
            except Exception:
                pass
    return issues


# ─── node-commands.ts ───

def find_node_binary() -> str | None:
    """Find node binary on PATH."""
    import shutil
    return shutil.which("node")


def find_bun_binary() -> str | None:
    import shutil
    return shutil.which("bun")


def run_node_command(
    script: str,
    args: list[str] | None = None,
    cwd: str | None = None,
    timeout_s: float = 30.0,
) -> tuple[int, str, str]:
    """Run a Node.js script. Returns (exit_code, stdout, stderr)."""
    node = find_node_binary()
    if not node:
        return -1, "", "node not found"
    cmd = [node, script] + (args or [])
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            cwd=cwd, timeout=timeout_s,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -1, "", str(e)


# ─── windows-task-restart.ts ───

@dataclass
class WindowsTaskRestartResult:
    ok: bool = False
    method: str = "schtasks"
    detail: str | None = None
    tried: list[str] = field(default_factory=list)


def relaunch_gateway_scheduled_task(
    task_name: str | None = None,
    env: dict[str, str] | None = None,
) -> WindowsTaskRestartResult:
    """Relaunch gateway via Windows scheduled task."""
    if sys.platform != "win32":
        return WindowsTaskRestartResult(
            ok=False, detail="not Windows",
            tried=[],
        )

    e = env or os.environ
    name = task_name or e.get("OPENCLAW_WINDOWS_TASK_NAME", "").strip() or "OpenClawGateway"

    try:
        import tempfile
        script_path = os.path.join(tempfile.gettempdir(),
                                   f"openclaw-schtasks-restart-{uuid.uuid4()}.cmd")
        retry_limit = 12
        retry_delay = 1
        script = "\r\n".join([
            "@echo off", "setlocal", "set /a attempts=0",
            ":retry",
            f"timeout /t {retry_delay} /nobreak >nul",
            "set /a attempts+=1",
            f'schtasks /Run /TN "{name}" >nul 2>&1',
            "if not errorlevel 1 goto cleanup",
            f"if %attempts% GEQ {retry_limit} goto cleanup",
            "goto retry",
            ":cleanup",
            'del "%~f0" >nul 2>&1',
        ])
        with open(script_path, "w") as f:
            f.write(script + "\r\n")

        subprocess.Popen(
            ["cmd.exe", "/d", "/s", "/c", script_path],
            creationflags=subprocess.DETACHED_PROCESS if hasattr(subprocess, "DETACHED_PROCESS") else 0,
            close_fds=True,
        )
        return WindowsTaskRestartResult(
            ok=True, method="schtasks",
            tried=[f'schtasks /Run /TN "{name}"', f"cmd.exe /d /s /c {script_path}"],
        )
    except Exception as e:
        return WindowsTaskRestartResult(
            ok=False, detail=str(e),
            tried=[f'schtasks /Run /TN "{name}"'],
        )
