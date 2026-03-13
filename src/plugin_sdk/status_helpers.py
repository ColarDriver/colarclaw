"""Plugin SDK status helpers — ported from bk/src/plugin-sdk/status-helpers.ts.

Channel runtime status snapshots, account status, issue collection.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ChannelRuntimeState:
    account_id: str = ""
    running: bool = False
    last_start_at: int | None = None
    last_stop_at: int | None = None
    last_error: str | None = None


def create_default_channel_runtime_state(account_id: str, **extra: Any) -> dict[str, Any]:
    return {
        "account_id": account_id,
        "running": False,
        "last_start_at": None,
        "last_stop_at": None,
        "last_error": None,
        **extra,
    }


def build_base_channel_status_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "configured": snapshot.get("configured", False),
        "running": snapshot.get("running", False),
        "last_start_at": snapshot.get("last_start_at") or snapshot.get("lastStartAt"),
        "last_stop_at": snapshot.get("last_stop_at") or snapshot.get("lastStopAt"),
        "last_error": snapshot.get("last_error") or snapshot.get("lastError"),
    }


def build_probe_channel_status_summary(snapshot: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        **build_base_channel_status_summary(snapshot),
        **extra,
        "probe": snapshot.get("probe"),
        "last_probe_at": snapshot.get("last_probe_at") or snapshot.get("lastProbeAt"),
    }


def build_base_account_status_snapshot(
    account: dict[str, Any],
    runtime: dict[str, Any] | None = None,
    probe: Any = None,
) -> dict[str, Any]:
    rt = runtime or {}
    return {
        "account_id": account.get("account_id", account.get("accountId", "")),
        "name": account.get("name"),
        "enabled": account.get("enabled"),
        "configured": account.get("configured"),
        **build_runtime_account_status_snapshot(rt, probe),
        "last_inbound_at": rt.get("last_inbound_at") or rt.get("lastInboundAt"),
        "last_outbound_at": rt.get("last_outbound_at") or rt.get("lastOutboundAt"),
    }


def build_computed_account_status_snapshot(
    account_id: str, name: str | None = None,
    enabled: bool | None = None, configured: bool | None = None,
    runtime: dict[str, Any] | None = None, probe: Any = None,
) -> dict[str, Any]:
    return build_base_account_status_snapshot(
        account={"account_id": account_id, "name": name, "enabled": enabled, "configured": configured},
        runtime=runtime, probe=probe,
    )


def build_runtime_account_status_snapshot(runtime: dict[str, Any] | None = None, probe: Any = None) -> dict[str, Any]:
    rt = runtime or {}
    return {
        "running": rt.get("running", False),
        "last_start_at": rt.get("last_start_at") or rt.get("lastStartAt"),
        "last_stop_at": rt.get("last_stop_at") or rt.get("lastStopAt"),
        "last_error": rt.get("last_error") or rt.get("lastError"),
        "probe": probe,
    }


def build_token_channel_status_summary(snapshot: dict[str, Any], include_mode: bool = True) -> dict[str, Any]:
    base = {
        **build_base_channel_status_summary(snapshot),
        "token_source": snapshot.get("token_source", snapshot.get("tokenSource", "none")),
        "probe": snapshot.get("probe"),
        "last_probe_at": snapshot.get("last_probe_at") or snapshot.get("lastProbeAt"),
    }
    if include_mode:
        base["mode"] = snapshot.get("mode")
    return base


@dataclass
class ChannelStatusIssue:
    channel: str = ""
    account_id: str = ""
    kind: str = "runtime"
    message: str = ""


def collect_status_issues_from_last_error(
    channel: str,
    accounts: list[dict[str, Any]],
) -> list[ChannelStatusIssue]:
    issues: list[ChannelStatusIssue] = []
    for account in accounts:
        last_error = account.get("last_error") or account.get("lastError") or ""
        if isinstance(last_error, str):
            last_error = last_error.strip()
        else:
            last_error = str(last_error).strip()
        if last_error:
            issues.append(ChannelStatusIssue(
                channel=channel,
                account_id=account.get("account_id", account.get("accountId", "")),
                kind="runtime",
                message=f"Channel error: {last_error}",
            ))
    return issues
