"""Auto-reply envelope — ported from bk/src/auto-reply/envelope.ts.

Formats inbound and agent envelopes with channel, sender, timestamps.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .types import AgentEnvelopeParams, EnvelopeFormatOptions


def _sanitize_header_part(value: str) -> str:
    result = re.sub(r"\r\n|\r|\n", " ", value)
    result = result.replace("[", "(").replace("]", ")")
    result = re.sub(r"\s+", " ", result)
    return result.strip()


def resolve_envelope_format_options(cfg: Any = None) -> EnvelopeFormatOptions:
    if not cfg:
        return EnvelopeFormatOptions()
    defaults = getattr(getattr(cfg, "agents", None), "defaults", None)
    if not defaults:
        return EnvelopeFormatOptions()
    return EnvelopeFormatOptions(
        timezone=getattr(defaults, "envelope_timezone", None),
        include_timestamp=getattr(defaults, "envelope_timestamp", None) != "off",
        include_elapsed=getattr(defaults, "envelope_elapsed", None) != "off",
        user_timezone=getattr(defaults, "user_timezone", None),
    )


def _format_time_ago(elapsed_ms: float) -> str | None:
    if elapsed_ms < 0:
        return None
    if elapsed_ms < 1000:
        return f"{int(elapsed_ms)}ms"
    seconds = elapsed_ms / 1000
    if seconds < 60:
        return f"{int(seconds)}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{int(minutes)}m"
    hours = minutes / 60
    if hours < 24:
        return f"{int(hours)}h"
    days = hours / 24
    return f"{int(days)}d"


def _format_timestamp(ts: float | None, options: EnvelopeFormatOptions | None = None) -> str | None:
    if ts is None:
        return None
    opts = options or EnvelopeFormatOptions()
    if not opts.include_timestamp:
        return None
    try:
        dt = datetime.fromtimestamp(ts / 1000 if ts > 1e12 else ts, tz=timezone.utc)
        weekday = dt.strftime("%a")
        formatted = dt.strftime("%Y-%m-%d %H:%M:%S %Z")
        return f"{weekday} {formatted}"
    except (ValueError, OSError):
        return None


def format_agent_envelope(params: AgentEnvelopeParams) -> str:
    channel = _sanitize_header_part(params.channel.strip() or "Channel")
    parts: list[str] = [channel]
    opts = params.envelope or EnvelopeFormatOptions()

    elapsed: str | None = None
    if opts.include_elapsed and params.timestamp and params.previous_timestamp:
        elapsed_ms = params.timestamp - params.previous_timestamp
        elapsed = _format_time_ago(elapsed_ms) if elapsed_ms >= 0 else None

    if params.from_ and params.from_.strip():
        from_part = _sanitize_header_part(params.from_.strip())
        parts.append(f"{from_part} +{elapsed}" if elapsed else from_part)
    elif elapsed:
        parts.append(f"+{elapsed}")

    if params.host and params.host.strip():
        parts.append(_sanitize_header_part(params.host.strip()))
    if params.ip and params.ip.strip():
        parts.append(_sanitize_header_part(params.ip.strip()))

    ts = _format_timestamp(params.timestamp, opts)
    if ts:
        parts.append(ts)

    header = f"[{' '.join(parts)}]"
    return f"{header} {params.body}"


def format_inbound_envelope(
    channel: str,
    from_: str,
    body: str,
    timestamp: float | None = None,
    chat_type: str | None = None,
    sender_label: str | None = None,
    previous_timestamp: float | None = None,
    envelope: EnvelopeFormatOptions | None = None,
    from_me: bool = False,
) -> str:
    is_direct = not chat_type or chat_type.strip().lower() == "direct"
    resolved_sender = _sanitize_header_part(sender_label.strip()) if sender_label and sender_label.strip() else ""

    if is_direct and from_me:
        final_body = f"(self): {body}"
    elif not is_direct and resolved_sender:
        final_body = f"{resolved_sender}: {body}"
    else:
        final_body = body

    return format_agent_envelope(AgentEnvelopeParams(
        channel=channel, from_=from_, timestamp=timestamp,
        previous_timestamp=previous_timestamp, envelope=envelope, body=final_body,
    ))


def format_inbound_from_label(
    is_group: bool,
    direct_label: str,
    group_label: str | None = None,
    group_id: str | None = None,
    direct_id: str | None = None,
    group_fallback: str | None = None,
) -> str:
    if is_group:
        label = (group_label or "").strip() or group_fallback or "Group"
        gid = (group_id or "").strip()
        return f"{label} id:{gid}" if gid else label
    dl = direct_label.strip()
    did = (direct_id or "").strip()
    if not did or did == dl:
        return dl
    return f"{dl} id:{did}"


def format_thread_starter_envelope(
    channel: str, body: str,
    author: str | None = None, timestamp: float | None = None,
    envelope: EnvelopeFormatOptions | None = None,
) -> str:
    return format_agent_envelope(AgentEnvelopeParams(
        channel=channel, from_=author, timestamp=timestamp,
        envelope=envelope, body=body,
    ))
