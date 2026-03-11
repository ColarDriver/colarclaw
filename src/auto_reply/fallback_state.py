"""Auto-reply fallback state — ported from bk/src/auto-reply/fallback-state.ts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .model_runtime import format_provider_model_ref

FALLBACK_REASON_PART_MAX = 80


def normalize_fallback_model_ref(value: str | None) -> str | None:
    trimmed = (value or "").strip()
    return trimmed or None


def _truncate_reason_part(value: str, max_len: int = FALLBACK_REASON_PART_MAX) -> str:
    import re
    text = re.sub(r"\s+", " ", value or "").strip()
    return text if len(text) <= max_len else f"{text[: max(0, max_len - 1)].rstrip()}…"


def format_fallback_attempt_reason(attempt: dict[str, Any]) -> str:
    reason = (attempt.get("reason") or "").strip()
    if reason:
        return reason.replace("_", " ")
    code = (attempt.get("code") or "").strip()
    if code:
        return code
    status = attempt.get("status")
    if isinstance(status, int):
        return f"HTTP {status}"
    return _truncate_reason_part(attempt.get("error") or "error")


def build_fallback_reason_summary(attempts: list[dict[str, Any]]) -> str:
    first = attempts[0] if attempts else None
    first_reason = format_fallback_attempt_reason(first) if first else "selected model unavailable"
    more = f" (+{len(attempts) - 1} more attempts)" if len(attempts) > 1 else ""
    return f"{_truncate_reason_part(first_reason)}{more}"


def build_fallback_attempt_summaries(attempts: list[dict[str, Any]]) -> list[str]:
    result = []
    for attempt in attempts:
        provider = attempt.get("provider", "")
        model = attempt.get("model", "")
        ref = format_provider_model_ref(provider, model)
        reason = format_fallback_attempt_reason(attempt)
        result.append(_truncate_reason_part(f"{ref} {reason}"))
    return result


def build_fallback_notice(
    selected_provider: str,
    selected_model: str,
    active_provider: str,
    active_model: str,
    attempts: list[dict[str, Any]],
) -> str | None:
    selected = format_provider_model_ref(selected_provider, selected_model)
    active = format_provider_model_ref(active_provider, active_model)
    if selected == active:
        return None
    reason = build_fallback_reason_summary(attempts)
    return f"↪️ Model Fallback: {active} (selected {selected}; {reason})"


def build_fallback_cleared_notice(
    selected_provider: str,
    selected_model: str,
    previous_active_model: str | None = None,
) -> str:
    selected = format_provider_model_ref(selected_provider, selected_model)
    previous = normalize_fallback_model_ref(previous_active_model)
    if previous and previous != selected:
        return f"↪️ Model Fallback cleared: {selected} (was {previous})"
    return f"↪️ Model Fallback cleared: {selected}"


@dataclass
class ResolvedFallbackTransition:
    selected_model_ref: str = ""
    active_model_ref: str = ""
    fallback_active: bool = False
    fallback_transitioned: bool = False
    fallback_cleared: bool = False
    reason_summary: str = ""
    attempt_summaries: list[str] = field(default_factory=list)
    previous_state: dict[str, str | None] = field(default_factory=dict)
    next_state: dict[str, str | None] = field(default_factory=dict)
    state_changed: bool = False


def resolve_fallback_transition(
    selected_provider: str,
    selected_model: str,
    active_provider: str,
    active_model: str,
    attempts: list[dict[str, Any]],
    state: Any = None,
) -> ResolvedFallbackTransition:
    selected_ref = format_provider_model_ref(selected_provider, selected_model)
    active_ref = format_provider_model_ref(active_provider, active_model)
    prev_selected = normalize_fallback_model_ref(getattr(state, "fallback_notice_selected_model", None)) if state else None
    prev_active = normalize_fallback_model_ref(getattr(state, "fallback_notice_active_model", None)) if state else None
    prev_reason = normalize_fallback_model_ref(getattr(state, "fallback_notice_reason", None)) if state else None

    fallback_active = selected_ref != active_ref
    fallback_transitioned = fallback_active and (prev_selected != selected_ref or prev_active != active_ref)
    fallback_cleared = not fallback_active and bool(prev_selected or prev_active)
    reason_summary = build_fallback_reason_summary(attempts)
    summaries = build_fallback_attempt_summaries(attempts)

    next_state = (
        {"selected_model": selected_ref, "active_model": active_ref, "reason": reason_summary}
        if fallback_active
        else {"selected_model": None, "active_model": None, "reason": None}
    )
    state_changed = prev_selected != next_state.get("selected_model") or prev_active != next_state.get("active_model") or prev_reason != next_state.get("reason")

    return ResolvedFallbackTransition(
        selected_model_ref=selected_ref,
        active_model_ref=active_ref,
        fallback_active=fallback_active,
        fallback_transitioned=fallback_transitioned,
        fallback_cleared=fallback_cleared,
        reason_summary=reason_summary,
        attempt_summaries=summaries,
        previous_state={"selected_model": prev_selected, "active_model": prev_active, "reason": prev_reason},
        next_state=next_state,
        state_changed=state_changed,
    )
