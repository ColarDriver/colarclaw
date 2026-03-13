"""Infra session cost — ported from bk/src/infra/session-cost-usage.ts,
session-cost-usage.types.ts, session-maintenance-warning.ts.

Session cost/usage tracking, daily breakdown, latency stats, model usage,
tool usage, maintenance warnings.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("infra.session_cost")


# ─── session-cost-usage.types.ts ───

@dataclass
class CostBreakdown:
    total: float = 0.0
    input: float = 0.0
    output: float = 0.0
    cache_read: float = 0.0
    cache_write: float = 0.0


@dataclass
class CostUsageTotals:
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    input_cost: float = 0.0
    output_cost: float = 0.0
    cache_read_cost: float = 0.0
    cache_write_cost: float = 0.0
    missing_cost_entries: int = 0


@dataclass
class CostUsageDailyEntry(CostUsageTotals):
    date: str = ""


@dataclass
class CostUsageSummary:
    updated_at: float = 0.0
    days: int = 0
    daily: list[CostUsageDailyEntry] = field(default_factory=list)
    totals: CostUsageTotals = field(default_factory=CostUsageTotals)


@dataclass
class SessionDailyUsage:
    date: str = ""  # YYYY-MM-DD
    tokens: int = 0
    cost: float = 0.0


@dataclass
class SessionDailyMessageCounts:
    date: str = ""
    total: int = 0
    user: int = 0
    assistant: int = 0
    tool_calls: int = 0
    tool_results: int = 0
    errors: int = 0


@dataclass
class SessionLatencyStats:
    count: int = 0
    avg_ms: float = 0.0
    p95_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0


@dataclass
class SessionDailyLatency(SessionLatencyStats):
    date: str = ""


@dataclass
class SessionDailyModelUsage:
    date: str = ""
    provider: str | None = None
    model: str | None = None
    tokens: int = 0
    cost: float = 0.0
    count: int = 0


@dataclass
class SessionMessageCounts:
    total: int = 0
    user: int = 0
    assistant: int = 0
    tool_calls: int = 0
    tool_results: int = 0
    errors: int = 0


@dataclass
class SessionToolUsage:
    total_calls: int = 0
    unique_tools: int = 0
    tools: list[dict[str, Any]] = field(default_factory=list)  # [{name, count}]


@dataclass
class SessionModelUsage:
    provider: str | None = None
    model: str | None = None
    count: int = 0
    totals: CostUsageTotals = field(default_factory=CostUsageTotals)


@dataclass
class SessionCostSummary(CostUsageTotals):
    session_id: str | None = None
    session_file: str | None = None
    first_activity: float | None = None
    last_activity: float | None = None
    duration_ms: int | None = None
    activity_dates: list[str] | None = None
    daily_breakdown: list[SessionDailyUsage] | None = None
    daily_message_counts: list[SessionDailyMessageCounts] | None = None
    daily_latency: list[SessionDailyLatency] | None = None
    daily_model_usage: list[SessionDailyModelUsage] | None = None
    message_counts: SessionMessageCounts | None = None
    tool_usage: SessionToolUsage | None = None
    model_usage: list[SessionModelUsage] | None = None
    latency: SessionLatencyStats | None = None


@dataclass
class DiscoveredSession:
    session_id: str = ""
    session_file: str = ""
    mtime: float = 0.0
    first_user_message: str | None = None


@dataclass
class SessionLogEntry:
    timestamp: float = 0.0
    role: str = ""  # "user" | "assistant" | "tool" | "toolResult"
    content: str = ""
    tokens: int | None = None
    cost: float | None = None


@dataclass
class ParsedUsageEntry:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_total: float | None = None
    cost_breakdown: CostBreakdown | None = None
    provider: str | None = None
    model: str | None = None
    timestamp: float | None = None


@dataclass
class ParsedTranscriptEntry:
    message: dict[str, Any] = field(default_factory=dict)
    role: str | None = None
    timestamp: float | None = None
    duration_ms: int | None = None
    cost_total: float | None = None
    cost_breakdown: CostBreakdown | None = None
    provider: str | None = None
    model: str | None = None
    stop_reason: str | None = None
    tool_names: list[str] = field(default_factory=list)
    tool_result_counts: dict[str, int] = field(default_factory=lambda: {"total": 0, "errors": 0})


# ─── session-cost-usage.ts: core aggregation ───

def create_empty_totals() -> CostUsageTotals:
    return CostUsageTotals()


def accumulate_usage(totals: CostUsageTotals, entry: ParsedUsageEntry) -> None:
    """Accumulate a usage entry into running totals."""
    totals.input += entry.input_tokens
    totals.output += entry.output_tokens
    totals.cache_read += entry.cache_read_tokens
    totals.cache_write += entry.cache_write_tokens
    totals.total_tokens += (entry.input_tokens + entry.output_tokens +
                            entry.cache_read_tokens + entry.cache_write_tokens)
    if entry.cost_total is not None:
        totals.total_cost += entry.cost_total
    else:
        totals.missing_cost_entries += 1
    if entry.cost_breakdown:
        totals.input_cost += entry.cost_breakdown.input
        totals.output_cost += entry.cost_breakdown.output
        totals.cache_read_cost += entry.cost_breakdown.cache_read
        totals.cache_write_cost += entry.cost_breakdown.cache_write


def compute_latency_stats(durations_ms: list[int | float]) -> SessionLatencyStats:
    """Compute latency statistics from a list of durations."""
    if not durations_ms:
        return SessionLatencyStats()
    sorted_durations = sorted(durations_ms)
    count = len(sorted_durations)
    avg = sum(sorted_durations) / count
    p95_idx = min(int(count * 0.95), count - 1)
    return SessionLatencyStats(
        count=count,
        avg_ms=round(avg, 1),
        p95_ms=float(sorted_durations[p95_idx]),
        min_ms=float(sorted_durations[0]),
        max_ms=float(sorted_durations[-1]),
    )


def compute_tool_usage(tool_names: list[str]) -> SessionToolUsage:
    """Compute tool usage summary from a list of tool call names."""
    counts: dict[str, int] = {}
    for name in tool_names:
        counts[name] = counts.get(name, 0) + 1
    tools = [{"name": name, "count": count} for name, count in sorted(counts.items(), key=lambda x: -x[1])]
    return SessionToolUsage(
        total_calls=len(tool_names),
        unique_tools=len(counts),
        tools=tools,
    )


def discover_sessions(sessions_dir: str) -> list[DiscoveredSession]:
    """Discover session files in the given directory."""
    sessions: list[DiscoveredSession] = []
    try:
        for entry in os.scandir(sessions_dir):
            if entry.is_file() and entry.name.endswith(".jsonl"):
                session_id = entry.name.rsplit(".", 1)[0]
                stat = entry.stat()
                sessions.append(DiscoveredSession(
                    session_id=session_id,
                    session_file=entry.path,
                    mtime=stat.st_mtime,
                ))
    except OSError:
        pass
    return sorted(sessions, key=lambda s: s.mtime, reverse=True)


def parse_session_log_entries(session_file: str) -> list[SessionLogEntry]:
    """Parse JSONL session log file into entries."""
    entries: list[SessionLogEntry] = []
    try:
        with open(session_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    entries.append(SessionLogEntry(
                        timestamp=data.get("timestamp", data.get("ts", 0)),
                        role=data.get("role", ""),
                        content=data.get("content", data.get("text", "")),
                        tokens=data.get("tokens"),
                        cost=data.get("cost"),
                    ))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return entries


# ─── session-maintenance-warning.ts ───

@dataclass
class MaintenanceWarning:
    kind: str = ""  # "approaching_limit" | "over_limit" | "session_old"
    message: str = ""
    severity: str = "info"  # "info" | "warn" | "error"


DEFAULT_TOKEN_WARN_THRESHOLD = 500_000
DEFAULT_TOKEN_ERROR_THRESHOLD = 1_000_000
DEFAULT_SESSION_AGE_WARN_DAYS = 30


def check_session_maintenance_warnings(
    totals: CostUsageTotals,
    first_activity: float | None = None,
    token_warn_threshold: int = DEFAULT_TOKEN_WARN_THRESHOLD,
    token_error_threshold: int = DEFAULT_TOKEN_ERROR_THRESHOLD,
    session_age_warn_days: int = DEFAULT_SESSION_AGE_WARN_DAYS,
) -> list[MaintenanceWarning]:
    """Check session for maintenance warnings."""
    warnings: list[MaintenanceWarning] = []

    if totals.total_tokens >= token_error_threshold:
        warnings.append(MaintenanceWarning(
            kind="over_limit",
            message=f"Session has used {totals.total_tokens:,} tokens (over {token_error_threshold:,} threshold). Consider starting a new session.",
            severity="error",
        ))
    elif totals.total_tokens >= token_warn_threshold:
        warnings.append(MaintenanceWarning(
            kind="approaching_limit",
            message=f"Session has used {totals.total_tokens:,} tokens (approaching {token_error_threshold:,} threshold).",
            severity="warn",
        ))

    if first_activity:
        age_days = (time.time() - first_activity) / 86400
        if age_days >= session_age_warn_days:
            warnings.append(MaintenanceWarning(
                kind="session_old",
                message=f"Session is {int(age_days)} days old. Consider archiving and starting a new session.",
                severity="warn",
            ))

    return warnings


# ─── session-cost-usage.ts: transcript scanning & loading ───

def _to_finite_number(value: Any) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    if not isinstance(value, int) and (value != value or value == float("inf") or value == float("-inf")):
        return None
    return float(value)


def _extract_cost_breakdown(usage_raw: dict[str, Any] | None) -> CostBreakdown | None:
    if not usage_raw or not isinstance(usage_raw, dict):
        return None
    cost = usage_raw.get("cost")
    if not isinstance(cost, dict):
        return None
    total = _to_finite_number(cost.get("total"))
    if total is None or total < 0:
        return None
    return CostBreakdown(
        total=total,
        input=_to_finite_number(cost.get("input")) or 0.0,
        output=_to_finite_number(cost.get("output")) or 0.0,
        cache_read=_to_finite_number(cost.get("cacheRead", cost.get("cache_read"))) or 0.0,
        cache_write=_to_finite_number(cost.get("cacheWrite", cost.get("cache_write"))) or 0.0,
    )


def _parse_timestamp(entry: dict[str, Any]) -> float | None:
    raw = entry.get("timestamp")
    if isinstance(raw, str):
        from datetime import datetime
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return dt.timestamp() * 1000
        except (ValueError, TypeError):
            pass
    message = entry.get("message")
    if isinstance(message, dict):
        ts = _to_finite_number(message.get("timestamp"))
        if ts is not None:
            return ts
    return None


def _format_day_key(ts_ms: float) -> str:
    from datetime import datetime, timezone
    dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d")


def _extract_tool_call_names(message: dict[str, Any]) -> list[str]:
    """Extract tool call names from a message object."""
    names: list[str] = []
    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                name = block.get("name", "")
                if isinstance(name, str) and name.strip():
                    names.append(name.strip())
    tool_calls = message.get("tool_calls") or message.get("toolCalls") or message.get("function_call") or message.get("functionCall")
    if tool_calls:
        if not isinstance(tool_calls, list):
            tool_calls = [tool_calls]
        for call in tool_calls:
            if isinstance(call, dict):
                name = call.get("name") or (call.get("function", {}) or {}).get("name", "")
                if isinstance(name, str) and name.strip():
                    names.append(name.strip())
    return names


def _count_tool_results(message: dict[str, Any]) -> dict[str, int]:
    """Count tool results in a message."""
    total = 0
    errors = 0
    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                total += 1
                if block.get("is_error") or block.get("isError"):
                    errors += 1
    return {"total": total, "errors": errors}


@dataclass
class ParsedTranscriptEntryFull:
    message: dict[str, Any] = field(default_factory=dict)
    role: str | None = None
    timestamp: float | None = None  # ms
    duration_ms: int | None = None
    cost_total: float | None = None
    cost_breakdown: CostBreakdown | None = None
    provider: str | None = None
    model: str | None = None
    stop_reason: str | None = None
    tool_names: list[str] = field(default_factory=list)
    tool_result_counts: dict[str, int] = field(default_factory=lambda: {"total": 0, "errors": 0})
    usage: dict[str, Any] | None = None


def _parse_transcript_entry(entry: dict[str, Any]) -> ParsedTranscriptEntryFull | None:
    message = entry.get("message")
    if not isinstance(message, dict):
        return None
    role = message.get("role")
    if role not in ("user", "assistant"):
        return None

    usage_raw = message.get("usage") or entry.get("usage")
    usage = None
    if isinstance(usage_raw, dict):
        usage = {
            "input": usage_raw.get("input", usage_raw.get("inputTokens", usage_raw.get("input_tokens", 0))),
            "output": usage_raw.get("output", usage_raw.get("outputTokens", usage_raw.get("output_tokens", 0))),
            "cacheRead": usage_raw.get("cacheRead", usage_raw.get("cache_read", usage_raw.get("cacheReadInputTokens", 0))),
            "cacheWrite": usage_raw.get("cacheWrite", usage_raw.get("cache_write", usage_raw.get("cacheCreationInputTokens", 0))),
        }
        total = usage_raw.get("total", usage_raw.get("totalTokens", usage_raw.get("total_tokens")))
        if total is not None:
            usage["total"] = total

    provider = message.get("provider") or entry.get("provider")
    model = message.get("model") or entry.get("model")
    cost_breakdown = _extract_cost_breakdown(usage_raw) if usage_raw else None
    stop_reason = message.get("stopReason") if isinstance(message.get("stopReason"), str) else None
    duration_ms_raw = message.get("durationMs", entry.get("durationMs"))
    duration_ms = int(duration_ms_raw) if isinstance(duration_ms_raw, (int, float)) and duration_ms_raw == duration_ms_raw else None

    return ParsedTranscriptEntryFull(
        message=message,
        role=role,
        timestamp=_parse_timestamp(entry),
        duration_ms=duration_ms,
        cost_total=cost_breakdown.total if cost_breakdown else None,
        cost_breakdown=cost_breakdown,
        provider=provider if isinstance(provider, str) else None,
        model=model if isinstance(model, str) else None,
        stop_reason=stop_reason,
        tool_names=_extract_tool_call_names(message),
        tool_result_counts=_count_tool_results(message),
        usage=usage,
    )


def _scan_transcript_file(file_path: str, on_entry: Any) -> None:
    """Scan a JSONL transcript file and call on_entry for each parsed entry."""
    try:
        with open(file_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                    if not isinstance(parsed, dict):
                        continue
                    entry = _parse_transcript_entry(parsed)
                    if entry:
                        on_entry(entry)
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass


def load_cost_usage_summary(
    start_ms: float | None = None,
    end_ms: float | None = None,
    days: int = 30,
    sessions_dir: str | None = None,
) -> CostUsageSummary:
    """Load aggregate cost/usage summary across all sessions."""
    import datetime
    now_ms = time.time() * 1000
    if start_ms is not None and end_ms is not None:
        since_time = start_ms
        until_time = end_ms
    else:
        d = max(1, days)
        since_time = now_ms - (d - 1) * 86_400_000
        until_time = now_ms

    if not sessions_dir:
        state_dir = os.path.join(str(Path.home()), ".openclaw")
        sessions_dir = os.path.join(state_dir, "sessions")

    daily_map: dict[str, CostUsageTotals] = {}
    totals = create_empty_totals()

    # Find transcript files
    try:
        for entry in os.scandir(sessions_dir):
            if not entry.is_file() or not entry.name.endswith(".jsonl"):
                continue
            try:
                stat = entry.stat()
                if stat.st_mtime * 1000 < since_time:
                    continue
            except OSError:
                continue

            def on_usage_entry(e: ParsedTranscriptEntryFull) -> None:
                if not e.usage:
                    return
                ts = e.timestamp
                if ts is None or ts < since_time or ts > until_time:
                    return
                day_key = _format_day_key(ts)
                bucket = daily_map.get(day_key) or create_empty_totals()
                _apply_usage_totals(bucket, e.usage)
                if e.cost_breakdown:
                    _apply_cost_breakdown(bucket, e.cost_breakdown)
                elif e.cost_total is not None:
                    bucket.total_cost += e.cost_total
                else:
                    bucket.missing_cost_entries += 1
                daily_map[day_key] = bucket
                _apply_usage_totals(totals, e.usage)
                if e.cost_breakdown:
                    _apply_cost_breakdown(totals, e.cost_breakdown)
                elif e.cost_total is not None:
                    totals.total_cost += e.cost_total
                else:
                    totals.missing_cost_entries += 1

            _scan_transcript_file(entry.path, on_usage_entry)
    except OSError:
        pass

    daily = sorted(
        [CostUsageDailyEntry(date=k, **{f.name: getattr(v, f.name) for f in v.__dataclass_fields__.values() if f.name != "date"})
         for k, v in daily_map.items()],
        key=lambda d: d.date,
    )
    computed_days = max(1, int((until_time - since_time) / 86_400_000) + 1)
    return CostUsageSummary(updated_at=now_ms, days=computed_days, daily=daily, totals=totals)


def _apply_usage_totals(totals: CostUsageTotals, usage: dict[str, Any]) -> None:
    totals.input += usage.get("input", 0) or 0
    totals.output += usage.get("output", 0) or 0
    totals.cache_read += usage.get("cacheRead", 0) or 0
    totals.cache_write += usage.get("cacheWrite", 0) or 0
    total_tokens = (
        usage.get("total")
        or ((usage.get("input", 0) or 0) + (usage.get("output", 0) or 0)
            + (usage.get("cacheRead", 0) or 0) + (usage.get("cacheWrite", 0) or 0))
    )
    totals.total_tokens += total_tokens


def _apply_cost_breakdown(totals: CostUsageTotals, breakdown: CostBreakdown) -> None:
    totals.total_cost += breakdown.total
    totals.input_cost += breakdown.input
    totals.output_cost += breakdown.output
    totals.cache_read_cost += breakdown.cache_read
    totals.cache_write_cost += breakdown.cache_write


def discover_all_sessions_full(sessions_dir: str,
                                start_ms: float | None = None,
                                end_ms: float | None = None) -> list[DiscoveredSession]:
    """Discover all sessions in a directory with first user message extraction."""
    discovered: list[DiscoveredSession] = []
    try:
        for entry in os.scandir(sessions_dir):
            if not entry.is_file() or not entry.name.endswith(".jsonl"):
                continue
            try:
                stat = entry.stat()
            except OSError:
                continue
            mtime_ms = stat.st_mtime * 1000
            if start_ms and mtime_ms < start_ms:
                continue
            session_id = entry.name[:-6]  # strip .jsonl

            first_user_message = None
            try:
                with open(entry.path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            parsed = json.loads(line)
                            msg = parsed.get("message") if isinstance(parsed, dict) else None
                            if isinstance(msg, dict) and msg.get("role") == "user":
                                content = msg.get("content")
                                if isinstance(content, str):
                                    first_user_message = content[:100]
                                elif isinstance(content, list):
                                    for block in content:
                                        if isinstance(block, dict) and block.get("type") == "text":
                                            text = block.get("text")
                                            if isinstance(text, str):
                                                first_user_message = text[:100]
                                            break
                                break
                        except json.JSONDecodeError:
                            continue
            except OSError:
                pass

            discovered.append(DiscoveredSession(
                session_id=session_id,
                session_file=entry.path,
                mtime=mtime_ms,
                first_user_message=first_user_message,
            ))
    except OSError:
        pass
    return sorted(discovered, key=lambda s: s.mtime, reverse=True)


def load_session_cost_summary(
    session_file: str,
    session_id: str | None = None,
    start_ms: float | None = None,
    end_ms: float | None = None,
) -> SessionCostSummary | None:
    """Load detailed cost summary for a single session."""
    if not os.path.isfile(session_file):
        return None

    totals = create_empty_totals()
    first_activity: float | None = None
    last_activity: float | None = None
    activity_dates: set[str] = set()
    daily_map: dict[str, dict[str, float]] = {}  # day -> {tokens, cost}
    daily_msg_map: dict[str, SessionDailyMessageCounts] = {}
    daily_latency_map: dict[str, list[float]] = {}
    daily_model_map: dict[str, SessionDailyModelUsage] = {}
    msg_counts = SessionMessageCounts()
    tool_usage_map: dict[str, int] = {}
    model_usage_map: dict[str, SessionModelUsage] = {}
    latency_values: list[float] = []
    last_user_ts: float | None = None
    MAX_LATENCY_MS = 12 * 3600 * 1000
    error_stop_reasons = {"error", "aborted", "timeout"}

    def on_entry(entry: ParsedTranscriptEntryFull) -> None:
        nonlocal first_activity, last_activity, last_user_ts
        ts = entry.timestamp
        if start_ms is not None and ts is not None and ts < start_ms:
            return
        if end_ms is not None and ts is not None and ts > end_ms:
            return
        if ts is not None:
            if first_activity is None or ts < first_activity:
                first_activity = ts
            if last_activity is None or ts > last_activity:
                last_activity = ts

        if entry.role == "user":
            msg_counts.user += 1
            msg_counts.total += 1
            if ts is not None:
                last_user_ts = ts
        if entry.role == "assistant":
            msg_counts.assistant += 1
            msg_counts.total += 1
            if ts is not None:
                latency_ms = entry.duration_ms
                if latency_ms is None and last_user_ts is not None:
                    latency_ms = max(0, int(ts - last_user_ts))
                if latency_ms is not None and 0 <= latency_ms <= MAX_LATENCY_MS:
                    latency_values.append(latency_ms)
                    day_key = _format_day_key(ts)
                    daily_latency_map.setdefault(day_key, []).append(latency_ms)

        if entry.tool_names:
            msg_counts.tool_calls += len(entry.tool_names)
            for name in entry.tool_names:
                tool_usage_map[name] = tool_usage_map.get(name, 0) + 1
        if entry.tool_result_counts["total"] > 0:
            msg_counts.tool_results += entry.tool_result_counts["total"]
            msg_counts.errors += entry.tool_result_counts["errors"]
        if entry.stop_reason and entry.stop_reason in error_stop_reasons:
            msg_counts.errors += 1

        if ts is not None:
            day_key = _format_day_key(ts)
            activity_dates.add(day_key)
            daily = daily_msg_map.get(day_key) or SessionDailyMessageCounts(date=day_key)
            if entry.role in ("user", "assistant"):
                daily.total += 1
            if entry.role == "user":
                daily.user += 1
            elif entry.role == "assistant":
                daily.assistant += 1
            daily.tool_calls += len(entry.tool_names)
            daily.tool_results += entry.tool_result_counts["total"]
            daily.errors += entry.tool_result_counts["errors"]
            if entry.stop_reason and entry.stop_reason in error_stop_reasons:
                daily.errors += 1
            daily_msg_map[day_key] = daily

        if not entry.usage:
            return

        _apply_usage_totals(totals, entry.usage)
        if entry.cost_breakdown:
            _apply_cost_breakdown(totals, entry.cost_breakdown)
        elif entry.cost_total is not None:
            totals.total_cost += entry.cost_total
        else:
            totals.missing_cost_entries += 1

        if ts is not None:
            day_key = _format_day_key(ts)
            entry_tokens = sum(entry.usage.get(k, 0) or 0 for k in ("input", "output", "cacheRead", "cacheWrite"))
            entry_cost = (
                entry.cost_breakdown.total if entry.cost_breakdown
                else (entry.cost_total or 0.0)
            )
            existing = daily_map.get(day_key) or {"tokens": 0, "cost": 0.0}
            daily_map[day_key] = {
                "tokens": existing["tokens"] + entry_tokens,
                "cost": existing["cost"] + entry_cost,
            }
            if entry.provider or entry.model:
                model_key = f"{day_key}::{entry.provider or 'unknown'}::{entry.model or 'unknown'}"
                dm = daily_model_map.get(model_key) or SessionDailyModelUsage(
                    date=day_key, provider=entry.provider, model=entry.model)
                dm.tokens += entry_tokens
                dm.cost += entry_cost
                dm.count += 1
                daily_model_map[model_key] = dm

        if entry.provider or entry.model:
            key = f"{entry.provider or 'unknown'}::{entry.model or 'unknown'}"
            existing_model = model_usage_map.get(key) or SessionModelUsage(
                provider=entry.provider, model=entry.model)
            existing_model.count += 1
            _apply_usage_totals(existing_model.totals, entry.usage)
            if entry.cost_breakdown:
                _apply_cost_breakdown(existing_model.totals, entry.cost_breakdown)
            elif entry.cost_total is not None:
                existing_model.totals.total_cost += entry.cost_total
            else:
                existing_model.totals.missing_cost_entries += 1
            model_usage_map[key] = existing_model

    _scan_transcript_file(session_file, on_entry)

    daily_breakdown = sorted(
        [SessionDailyUsage(date=k, tokens=int(v["tokens"]), cost=v["cost"]) for k, v in daily_map.items()],
        key=lambda d: d.date,
    )
    daily_message_counts_list = sorted(daily_msg_map.values(), key=lambda d: d.date)
    daily_latency_list = sorted(
        [SessionDailyLatency(date=k, **compute_latency_stats(v).__dict__)
         for k, v in daily_latency_map.items() if v],
        key=lambda d: d.date,
    )
    daily_model_list = sorted(daily_model_map.values(), key=lambda d: (d.date, -d.cost))
    tool_usage = compute_tool_usage(
        [name for name, cnt in tool_usage_map.items() for _ in range(cnt)]
    ) if tool_usage_map else None
    model_usage_list = sorted(model_usage_map.values(),
                               key=lambda m: (-m.totals.total_cost, -m.totals.total_tokens)) if model_usage_map else None

    return SessionCostSummary(
        session_id=session_id,
        session_file=session_file,
        first_activity=first_activity,
        last_activity=last_activity,
        duration_ms=int(max(0, last_activity - first_activity)) if first_activity is not None and last_activity is not None else None,
        activity_dates=sorted(activity_dates) if activity_dates else None,
        daily_breakdown=daily_breakdown or None,
        daily_message_counts=daily_message_counts_list or None,
        daily_latency=daily_latency_list or None,
        daily_model_usage=daily_model_list or None,
        message_counts=msg_counts,
        tool_usage=tool_usage,
        model_usage=model_usage_list,
        latency=compute_latency_stats(latency_values) if latency_values else None,
        input=totals.input, output=totals.output,
        cache_read=totals.cache_read, cache_write=totals.cache_write,
        total_tokens=totals.total_tokens, total_cost=totals.total_cost,
        input_cost=totals.input_cost, output_cost=totals.output_cost,
        cache_read_cost=totals.cache_read_cost, cache_write_cost=totals.cache_write_cost,
        missing_cost_entries=totals.missing_cost_entries,
    )


@dataclass
class SessionUsageTimePoint:
    timestamp: float = 0.0
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    cumulative_tokens: int = 0
    cumulative_cost: float = 0.0


@dataclass
class SessionUsageTimeSeries:
    session_id: str | None = None
    points: list[SessionUsageTimePoint] = field(default_factory=list)


def load_session_usage_time_series(
    session_file: str,
    session_id: str | None = None,
    max_points: int = 100,
) -> SessionUsageTimeSeries | None:
    """Load cumulative usage time series for a session."""
    if not os.path.isfile(session_file):
        return None

    points: list[SessionUsageTimePoint] = []
    cumulative_tokens = 0
    cumulative_cost = 0.0

    def on_entry(entry: ParsedTranscriptEntryFull) -> None:
        nonlocal cumulative_tokens, cumulative_cost
        if not entry.usage or entry.timestamp is None:
            return
        inp = entry.usage.get("input", 0) or 0
        out = entry.usage.get("output", 0) or 0
        cr = entry.usage.get("cacheRead", 0) or 0
        cw = entry.usage.get("cacheWrite", 0) or 0
        total_t = entry.usage.get("total") or (inp + out + cr + cw)
        cost = entry.cost_total or 0.0
        cumulative_tokens += total_t
        cumulative_cost += cost
        points.append(SessionUsageTimePoint(
            timestamp=entry.timestamp, input=inp, output=out,
            cache_read=cr, cache_write=cw, total_tokens=total_t,
            cost=cost, cumulative_tokens=cumulative_tokens,
            cumulative_cost=cumulative_cost,
        ))

    _scan_transcript_file(session_file, on_entry)
    sorted_points = sorted(points, key=lambda p: p.timestamp)

    # Downsample if too many points
    if len(sorted_points) > max_points:
        step = len(sorted_points) // max_points
        downsampled: list[SessionUsageTimePoint] = []
        ds_cum_tokens = 0
        ds_cum_cost = 0.0
        for i in range(0, len(sorted_points), step):
            bucket = sorted_points[i:i + step]
            if not bucket:
                continue
            last = bucket[-1]
            b_in = sum(p.input for p in bucket)
            b_out = sum(p.output for p in bucket)
            b_cr = sum(p.cache_read for p in bucket)
            b_cw = sum(p.cache_write for p in bucket)
            b_tok = sum(p.total_tokens for p in bucket)
            b_cost = sum(p.cost for p in bucket)
            ds_cum_tokens += b_tok
            ds_cum_cost += b_cost
            downsampled.append(SessionUsageTimePoint(
                timestamp=last.timestamp, input=b_in, output=b_out,
                cache_read=b_cr, cache_write=b_cw, total_tokens=b_tok,
                cost=b_cost, cumulative_tokens=ds_cum_tokens,
                cumulative_cost=ds_cum_cost,
            ))
        return SessionUsageTimeSeries(session_id=session_id, points=downsampled)

    return SessionUsageTimeSeries(session_id=session_id, points=sorted_points)


def load_session_logs(
    session_file: str,
    limit: int = 50,
) -> list[SessionLogEntry] | None:
    """Load parsed session log entries for UI display."""
    if not os.path.isfile(session_file):
        return None

    logs: list[SessionLogEntry] = []
    try:
        with open(session_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                    if not isinstance(parsed, dict):
                        continue
                    message = parsed.get("message")
                    if not isinstance(message, dict):
                        continue
                    role = message.get("role")
                    if role not in ("user", "assistant", "tool", "toolResult"):
                        continue

                    content_parts: list[str] = []
                    raw_tool_name = message.get("toolName") or message.get("tool_name") or message.get("name") or message.get("tool")
                    tool_name = raw_tool_name.strip() if isinstance(raw_tool_name, str) and raw_tool_name.strip() else None

                    if role in ("tool", "toolResult"):
                        content_parts.append(f"[Tool: {tool_name or 'tool'}]")
                        content_parts.append("[Tool Result]")

                    raw_content = message.get("content")
                    if isinstance(raw_content, str):
                        content_parts.append(raw_content)
                    elif isinstance(raw_content, list):
                        for block in raw_content:
                            if isinstance(block, str):
                                content_parts.append(block)
                            elif isinstance(block, dict):
                                if block.get("type") == "text" and isinstance(block.get("text"), str):
                                    content_parts.append(block["text"])
                                elif block.get("type") == "tool_use":
                                    name = block.get("name", "unknown")
                                    content_parts.append(f"[Tool: {name}]")
                                elif block.get("type") == "tool_result":
                                    content_parts.append("[Tool Result]")

                    # OpenAI-style tool calls
                    raw_calls = message.get("tool_calls") or message.get("toolCalls") or message.get("function_call") or message.get("functionCall")
                    if raw_calls:
                        if not isinstance(raw_calls, list):
                            raw_calls = [raw_calls]
                        for call in raw_calls:
                            if isinstance(call, dict):
                                name = call.get("name") or (call.get("function", {}) or {}).get("name", "unknown")
                                content_parts.append(f"[Tool: {name}]")

                    content = "\n".join(content_parts).strip()
                    if not content:
                        continue
                    if len(content) > 2000:
                        content = content[:2000] + "…"

                    timestamp = 0.0
                    if isinstance(parsed.get("timestamp"), str):
                        from datetime import datetime
                        try:
                            dt = datetime.fromisoformat(parsed["timestamp"].replace("Z", "+00:00"))
                            timestamp = dt.timestamp() * 1000
                        except (ValueError, TypeError):
                            pass
                    elif isinstance(message.get("timestamp"), (int, float)):
                        timestamp = float(message["timestamp"])

                    tokens = None
                    cost = None
                    if role == "assistant":
                        usage_raw = message.get("usage")
                        if isinstance(usage_raw, dict):
                            inp = usage_raw.get("input", usage_raw.get("inputTokens", 0)) or 0
                            out = usage_raw.get("output", usage_raw.get("outputTokens", 0)) or 0
                            cr = usage_raw.get("cacheRead", usage_raw.get("cache_read", 0)) or 0
                            cw = usage_raw.get("cacheWrite", usage_raw.get("cache_write", 0)) or 0
                            tokens = usage_raw.get("total", usage_raw.get("totalTokens")) or (inp + out + cr + cw)
                            breakdown = _extract_cost_breakdown(usage_raw)
                            if breakdown and breakdown.total is not None:
                                cost = breakdown.total

                    logs.append(SessionLogEntry(
                        timestamp=timestamp, role=role, content=content,
                        tokens=tokens, cost=cost,
                    ))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return None

    sorted_logs = sorted(logs, key=lambda l: l.timestamp)
    if len(sorted_logs) > limit:
        return sorted_logs[-limit:]
    return sorted_logs
