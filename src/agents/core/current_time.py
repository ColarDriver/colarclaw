"""Current time helpers — ported from bk/src/agents/current-time.ts."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from agents.date_time import format_user_time, resolve_user_time_format, resolve_user_timezone

@dataclass
class CronStyleNow:
    user_timezone: str
    formatted_time: str
    time_line: str

def resolve_cron_style_now(cfg: dict[str, Any], now_ms: float) -> CronStyleNow:
    defaults = cfg.get("agents", {}).get("defaults", {})
    user_tz = resolve_user_timezone(defaults.get("userTimezone"))
    user_fmt = resolve_user_time_format(defaults.get("timeFormat"))
    dt = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc)
    formatted = format_user_time(dt, user_tz, user_fmt) or dt.isoformat()
    utc_time = dt.strftime("%Y-%m-%d %H:%M") + " UTC"
    time_line = f"Current time: {formatted} ({user_tz}) / {utc_time}"
    return CronStyleNow(user_timezone=user_tz, formatted_time=formatted, time_line=time_line)

def append_cron_style_current_time_line(text: str, cfg: dict[str, Any], now_ms: float) -> str:
    base = text.rstrip()
    if not base or "Current time:" in base:
        return base
    result = resolve_cron_style_now(cfg, now_ms)
    return f"{base}\n{result.time_line}"
