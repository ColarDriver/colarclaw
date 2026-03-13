"""Shared usage types and aggregates — ported from bk/src/shared/usage-types.ts,
usage-aggregates.ts, session-types.ts, session-usage-timeseries-types.ts.

Usage metrics types, latency aggregation, and session type definitions.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


# ─── usage-types.ts ───

@dataclass
class UsageSummary:
    total_cost: float = 0.0
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    request_count: int = 0
    image_count: int = 0
    audio_seconds: float = 0.0


@dataclass
class ModelUsage:
    model_id: str = ""
    provider: str = ""
    cost: float = 0.0
    tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    requests: int = 0


# ─── session-types.ts ───

@dataclass
class SessionType:
    session_id: str = ""
    channel: str = ""
    account_id: str = ""
    sender_id: str = ""
    started_at_ms: int = 0
    ended_at_ms: int = 0
    message_count: int = 0
    total_cost: float = 0.0


# ─── session-usage-timeseries-types.ts ───

@dataclass
class SessionUsageTimeseriesEntry:
    date: str = ""
    session_count: int = 0
    message_count: int = 0
    total_cost: float = 0.0
    tokens: int = 0


# ─── usage-aggregates.ts ───

@dataclass
class LatencyTotals:
    count: int = 0
    sum: float = 0.0
    min: float = math.inf
    max: float = 0.0
    p95_max: float = 0.0


@dataclass
class DailyLatency:
    date: str = ""
    count: int = 0
    sum: float = 0.0
    min: float = math.inf
    max: float = 0.0
    p95_max: float = 0.0


@dataclass
class LatencyResult:
    count: int = 0
    avg_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    p95_ms: float = 0.0


def merge_usage_latency(
    totals: LatencyTotals,
    latency: dict[str, Any] | None,
) -> None:
    """Merge a latency entry into running totals."""
    if not latency or latency.get("count", 0) <= 0:
        return
    count = latency["count"]
    totals.count += count
    totals.sum += latency.get("avgMs", 0) * count
    totals.min = min(totals.min, latency.get("minMs", math.inf))
    totals.max = max(totals.max, latency.get("maxMs", 0))
    totals.p95_max = max(totals.p95_max, latency.get("p95Ms", 0))


def merge_usage_daily_latency(
    daily_map: dict[str, DailyLatency],
    daily_latency: list[dict[str, Any]] | None = None,
) -> None:
    """Merge daily latency entries into a map."""
    for day in (daily_latency or []):
        date = day.get("date", "")
        existing = daily_map.get(date)
        if not existing:
            existing = DailyLatency(date=date)
            daily_map[date] = existing
        count = day.get("count", 0)
        existing.count += count
        existing.sum += day.get("avgMs", 0) * count
        existing.min = min(existing.min, day.get("minMs", math.inf))
        existing.max = max(existing.max, day.get("maxMs", 0))
        existing.p95_max = max(existing.p95_max, day.get("p95Ms", 0))


def finalize_latency_totals(totals: LatencyTotals) -> LatencyResult | None:
    if totals.count <= 0:
        return None
    return LatencyResult(
        count=totals.count,
        avg_ms=totals.sum / totals.count,
        min_ms=0 if totals.min == math.inf else totals.min,
        max_ms=totals.max,
        p95_ms=totals.p95_max,
    )


def finalize_daily_latency(daily_map: dict[str, DailyLatency]) -> list[dict[str, Any]]:
    result = []
    for entry in sorted(daily_map.values(), key=lambda e: e.date):
        result.append({
            "date": entry.date,
            "count": entry.count,
            "avgMs": entry.sum / entry.count if entry.count else 0,
            "minMs": 0 if entry.min == math.inf else entry.min,
            "maxMs": entry.max,
            "p95Ms": entry.p95_max,
        })
    return result


def build_usage_aggregate_tail(
    by_channel_map: dict[str, Any],
    latency_totals: LatencyTotals,
    daily_latency_map: dict[str, DailyLatency],
    model_daily_map: dict[str, Any],
    daily_map: dict[str, Any],
) -> dict[str, Any]:
    """Build the tail of a usage aggregate response."""
    by_channel = sorted(
        [{"channel": k, "totals": v} for k, v in by_channel_map.items()],
        key=lambda x: -(x["totals"].get("totalCost", 0) if isinstance(x["totals"], dict) else 0),
    )
    return {
        "byChannel": by_channel,
        "latency": finalize_latency_totals(latency_totals),
        "dailyLatency": finalize_daily_latency(daily_latency_map),
        "modelDaily": sorted(model_daily_map.values(), key=lambda x: (x.get("date", ""), -x.get("cost", 0))),
        "daily": sorted(daily_map.values(), key=lambda x: x.get("date", "")),
    }
