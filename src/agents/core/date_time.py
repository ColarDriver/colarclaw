"""Date/time helpers — ported from bk/src/agents/date-time.ts."""
from __future__ import annotations
import math
import re
from datetime import datetime, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo

TimeFormatPreference = Literal["auto", "12", "24"]
ResolvedTimeFormat = Literal["12", "24"]

_cached_time_format: ResolvedTimeFormat | None = None

def resolve_user_timezone(configured: str | None = None) -> str:
    trimmed = (configured or "").strip()
    if trimmed:
        try:
            ZoneInfo(trimmed)
            return trimmed
        except (KeyError, ValueError):
            pass
    try:
        import time as _time
        local_tz = _time.tzname[0]
        if local_tz:
            return local_tz
    except Exception:
        pass
    return "UTC"

def resolve_user_time_format(preference: TimeFormatPreference | None = None) -> ResolvedTimeFormat:
    global _cached_time_format
    if preference in ("12", "24"):
        return preference  # type: ignore
    if _cached_time_format:
        return _cached_time_format
    _cached_time_format = "24"
    return _cached_time_format

def normalize_timestamp(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    ts_ms: float | None = None
    if isinstance(raw, datetime):
        ts_ms = raw.timestamp() * 1000
    elif isinstance(raw, (int, float)) and math.isfinite(raw):
        ts_ms = raw * 1000 if raw < 1_000_000_000_000 else raw
    elif isinstance(raw, str):
        trimmed = raw.strip()
        if not trimmed:
            return None
        if re.match(r"^\d+(\.\d+)?$", trimmed):
            num = float(trimmed)
            if math.isfinite(num):
                if "." in trimmed:
                    ts_ms = round(num * 1000)
                elif len(trimmed) >= 13:
                    ts_ms = round(num)
                else:
                    ts_ms = round(num * 1000)
        else:
            try:
                parsed = datetime.fromisoformat(trimmed.replace("Z", "+00:00"))
                ts_ms = parsed.timestamp() * 1000
            except (ValueError, TypeError):
                pass
    if ts_ms is None or not math.isfinite(ts_ms):
        return None
    ts_ms = round(ts_ms)
    return {
        "timestampMs": ts_ms,
        "timestampUtc": datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
    }

def _ordinal_suffix(day: int) -> str:
    if 11 <= day <= 13:
        return "th"
    r = day % 10
    if r == 1: return "st"
    if r == 2: return "nd"
    if r == 3: return "rd"
    return "th"

def format_user_time(
    dt: datetime, tz_name: str, fmt: ResolvedTimeFormat,
) -> str | None:
    try:
        tz = ZoneInfo(tz_name)
        local_dt = dt.astimezone(tz)
        weekday = local_dt.strftime("%A")
        month = local_dt.strftime("%B")
        day = local_dt.day
        year = local_dt.year
        suffix = _ordinal_suffix(day)
        if fmt == "24":
            time_part = local_dt.strftime("%H:%M")
        else:
            time_part = local_dt.strftime("%I:%M %p").lstrip("0")
        return f"{weekday}, {month} {day}{suffix}, {year} — {time_part}"
    except Exception:
        return None
