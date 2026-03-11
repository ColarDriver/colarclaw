"""Tool loop detection — ported from bk/src/agents/tool-loop-detection.ts.

Detects when an agent is stuck in a repetitive tool call loop by checking
for generic-repeat, poll-no-progress, ping-pong, and global circuit breaker
patterns.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal

log = logging.getLogger("openclaw.agents.loop_detection")

LoopDetectorKind = Literal["generic_repeat", "known_poll_no_progress", "global_circuit_breaker", "ping_pong"]

TOOL_CALL_HISTORY_SIZE = 30
WARNING_THRESHOLD = 10
CRITICAL_THRESHOLD = 20
GLOBAL_CIRCUIT_BREAKER_THRESHOLD = 30

_DEFAULT_CONFIG = {
    "enabled": False,
    "history_size": TOOL_CALL_HISTORY_SIZE,
    "warning_threshold": WARNING_THRESHOLD,
    "critical_threshold": CRITICAL_THRESHOLD,
    "global_circuit_breaker_threshold": GLOBAL_CIRCUIT_BREAKER_THRESHOLD,
    "detectors": {
        "generic_repeat": True,
        "known_poll_no_progress": True,
        "ping_pong": True,
    },
}


@dataclass
class LoopDetectionResult:
    stuck: bool = False
    level: str | None = None  # "warning" | "critical"
    detector: str | None = None
    count: int = 0
    message: str = ""
    paired_tool_name: str | None = None
    warning_key: str | None = None


@dataclass
class _ResolvedConfig:
    enabled: bool
    history_size: int
    warning_threshold: int
    critical_threshold: int
    global_circuit_breaker_threshold: int
    detectors_generic_repeat: bool
    detectors_known_poll_no_progress: bool
    detectors_ping_pong: bool


@dataclass
class ToolCallHistoryEntry:
    tool_name: str
    args_hash: str
    tool_call_id: str | None = None
    result_hash: str | None = None
    timestamp: float = field(default_factory=lambda: time.time() * 1000)


def _as_positive_int(value: int | None, fallback: int) -> int:
    if value is None or not isinstance(value, int) or value <= 0:
        return fallback
    return value


def _resolve_config(config: dict[str, Any] | None = None) -> _ResolvedConfig:
    cfg = config or {}
    warning = _as_positive_int(cfg.get("warning_threshold") or cfg.get("warningThreshold"), WARNING_THRESHOLD)
    critical = _as_positive_int(cfg.get("critical_threshold") or cfg.get("criticalThreshold"), CRITICAL_THRESHOLD)
    global_cb = _as_positive_int(cfg.get("global_circuit_breaker_threshold") or cfg.get("globalCircuitBreakerThreshold"), GLOBAL_CIRCUIT_BREAKER_THRESHOLD)
    if critical <= warning:
        critical = warning + 1
    if global_cb <= critical:
        global_cb = critical + 1
    detectors = cfg.get("detectors", {}) or {}
    return _ResolvedConfig(
        enabled=cfg.get("enabled", False),
        history_size=_as_positive_int(cfg.get("history_size") or cfg.get("historySize"), TOOL_CALL_HISTORY_SIZE),
        warning_threshold=warning,
        critical_threshold=critical,
        global_circuit_breaker_threshold=global_cb,
        detectors_generic_repeat=detectors.get("generic_repeat", detectors.get("genericRepeat", True)),
        detectors_known_poll_no_progress=detectors.get("known_poll_no_progress", detectors.get("knownPollNoProgress", True)),
        detectors_ping_pong=detectors.get("ping_pong", detectors.get("pingPong", True)),
    )


def _stable_stringify(value: Any) -> str:
    if value is None or not isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, list):
        return "[" + ",".join(_stable_stringify(v) for v in value) + "]"
    keys = sorted(value.keys())
    items = ",".join(f"{json.dumps(k)}:{_stable_stringify(value[k])}" for k in keys)
    return "{" + items + "}"


def _digest_stable(value: Any) -> str:
    try:
        serialized = _stable_stringify(value)
    except Exception:
        serialized = str(value)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def hash_tool_call(tool_name: str, params: Any) -> str:
    return f"{tool_name}:{_digest_stable(params)}"


def _is_known_poll_tool_call(tool_name: str, params: Any) -> bool:
    if tool_name == "command_status":
        return True
    if tool_name != "process" or not isinstance(params, dict):
        return False
    action = params.get("action")
    return action in ("poll", "log")


def _get_no_progress_streak(
    history: list[ToolCallHistoryEntry],
    tool_name: str,
    args_hash: str,
) -> tuple[int, str | None]:
    streak = 0
    latest_result_hash: str | None = None
    for entry in reversed(history):
        if entry.tool_name != tool_name or entry.args_hash != args_hash:
            continue
        if not entry.result_hash:
            continue
        if latest_result_hash is None:
            latest_result_hash = entry.result_hash
            streak = 1
            continue
        if entry.result_hash != latest_result_hash:
            break
        streak += 1
    return streak, latest_result_hash


def _get_ping_pong_streak(
    history: list[ToolCallHistoryEntry],
    current_signature: str,
) -> dict[str, Any]:
    if not history:
        return {"count": 0, "no_progress_evidence": False}
    last = history[-1]
    other_signature: str | None = None
    other_tool_name: str | None = None
    for i in range(len(history) - 2, -1, -1):
        call = history[i]
        if call.args_hash != last.args_hash:
            other_signature = call.args_hash
            other_tool_name = call.tool_name
            break
    if not other_signature or not other_tool_name:
        return {"count": 0, "no_progress_evidence": False}

    alternating_count = 0
    for i in range(len(history) - 1, -1, -1):
        call = history[i]
        expected = last.args_hash if alternating_count % 2 == 0 else other_signature
        if call.args_hash != expected:
            break
        alternating_count += 1
    if alternating_count < 2:
        return {"count": 0, "no_progress_evidence": False}
    if current_signature != other_signature:
        return {"count": 0, "no_progress_evidence": False}

    tail_start = max(0, len(history) - alternating_count)
    first_hash_a: str | None = None
    first_hash_b: str | None = None
    no_progress = True
    for i in range(tail_start, len(history)):
        call = history[i]
        if not call.result_hash:
            no_progress = False
            break
        if call.args_hash == last.args_hash:
            if first_hash_a is None:
                first_hash_a = call.result_hash
            elif first_hash_a != call.result_hash:
                no_progress = False
                break
        elif call.args_hash == other_signature:
            if first_hash_b is None:
                first_hash_b = call.result_hash
            elif first_hash_b != call.result_hash:
                no_progress = False
                break
        else:
            no_progress = False
            break
    if not first_hash_a or not first_hash_b:
        no_progress = False

    return {
        "count": alternating_count + 1,
        "paired_tool_name": last.tool_name,
        "paired_signature": last.args_hash,
        "no_progress_evidence": no_progress,
    }


def _canonical_pair_key(sig_a: str, sig_b: str) -> str:
    return "|".join(sorted([sig_a, sig_b]))


def detect_tool_call_loop(
    state: dict[str, Any],
    tool_name: str,
    params: Any,
    config: dict[str, Any] | None = None,
) -> LoopDetectionResult:
    """Detect if an agent is stuck in a repetitive tool call loop."""
    resolved = _resolve_config(config)
    if not resolved.enabled:
        return LoopDetectionResult()

    history: list[ToolCallHistoryEntry] = state.get("tool_call_history", [])
    current_hash = hash_tool_call(tool_name, params)
    no_progress_streak, latest_result_hash = _get_no_progress_streak(history, tool_name, current_hash)
    known_poll_tool = _is_known_poll_tool_call(tool_name, params)
    ping_pong = _get_ping_pong_streak(history, current_hash)

    if no_progress_streak >= resolved.global_circuit_breaker_threshold:
        return LoopDetectionResult(
            stuck=True, level="critical", detector="global_circuit_breaker",
            count=no_progress_streak,
            message=f"CRITICAL: {tool_name} has repeated identical no-progress outcomes {no_progress_streak} times. Session execution blocked by global circuit breaker.",
            warning_key=f"global:{tool_name}:{current_hash}:{latest_result_hash or 'none'}",
        )

    if known_poll_tool and resolved.detectors_known_poll_no_progress:
        if no_progress_streak >= resolved.critical_threshold:
            return LoopDetectionResult(
                stuck=True, level="critical", detector="known_poll_no_progress",
                count=no_progress_streak,
                message=f"CRITICAL: Called {tool_name} with identical arguments and no progress {no_progress_streak} times. Stuck polling loop.",
                warning_key=f"poll:{tool_name}:{current_hash}:{latest_result_hash or 'none'}",
            )
        if no_progress_streak >= resolved.warning_threshold:
            return LoopDetectionResult(
                stuck=True, level="warning", detector="known_poll_no_progress",
                count=no_progress_streak,
                message=f"WARNING: You have called {tool_name} {no_progress_streak} times with identical arguments and no progress.",
                warning_key=f"poll:{tool_name}:{current_hash}:{latest_result_hash or 'none'}",
            )

    pp_warning_key = (
        f"pingpong:{_canonical_pair_key(current_hash, ping_pong['paired_signature'])}"
        if ping_pong.get("paired_signature")
        else f"pingpong:{tool_name}:{current_hash}"
    )

    if resolved.detectors_ping_pong and ping_pong["count"] >= resolved.critical_threshold and ping_pong["no_progress_evidence"]:
        return LoopDetectionResult(
            stuck=True, level="critical", detector="ping_pong",
            count=ping_pong["count"],
            message=f"CRITICAL: Alternating tool-call patterns ({ping_pong['count']} calls) with no progress. Stuck ping-pong loop.",
            paired_tool_name=ping_pong.get("paired_tool_name"),
            warning_key=pp_warning_key,
        )
    if resolved.detectors_ping_pong and ping_pong["count"] >= resolved.warning_threshold:
        return LoopDetectionResult(
            stuck=True, level="warning", detector="ping_pong",
            count=ping_pong["count"],
            message=f"WARNING: Alternating tool-call patterns ({ping_pong['count']} calls). Looks like a ping-pong loop.",
            paired_tool_name=ping_pong.get("paired_tool_name"),
            warning_key=pp_warning_key,
        )

    recent_count = sum(1 for h in history if h.tool_name == tool_name and h.args_hash == current_hash)
    if not known_poll_tool and resolved.detectors_generic_repeat and recent_count >= resolved.warning_threshold:
        return LoopDetectionResult(
            stuck=True, level="warning", detector="generic_repeat",
            count=recent_count,
            message=f"WARNING: {tool_name} called {recent_count} times with identical arguments.",
            warning_key=f"generic:{tool_name}:{current_hash}",
        )

    return LoopDetectionResult()


def record_tool_call(
    state: dict[str, Any],
    tool_name: str,
    params: Any,
    tool_call_id: str | None = None,
    config: dict[str, Any] | None = None,
) -> None:
    """Record a tool call in session history for loop detection."""
    resolved = _resolve_config(config)
    if "tool_call_history" not in state:
        state["tool_call_history"] = []
    state["tool_call_history"].append(ToolCallHistoryEntry(
        tool_name=tool_name,
        args_hash=hash_tool_call(tool_name, params),
        tool_call_id=tool_call_id,
    ))
    if len(state["tool_call_history"]) > resolved.history_size:
        state["tool_call_history"].pop(0)


def record_tool_call_outcome(
    state: dict[str, Any],
    tool_name: str,
    tool_params: Any,
    tool_call_id: str | None = None,
    result: Any = None,
    error: Any = None,
    config: dict[str, Any] | None = None,
) -> None:
    """Record a completed tool call outcome for no-progress detection."""
    resolved = _resolve_config(config)
    result_hash = _digest_stable({"result": result, "error": str(error) if error else None})
    if "tool_call_history" not in state:
        state["tool_call_history"] = []
    args_hash = hash_tool_call(tool_name, tool_params)
    matched = False
    for entry in reversed(state["tool_call_history"]):
        if tool_call_id and entry.tool_call_id != tool_call_id:
            continue
        if entry.tool_name != tool_name or entry.args_hash != args_hash:
            continue
        if entry.result_hash is not None:
            continue
        entry.result_hash = result_hash
        matched = True
        break
    if not matched:
        state["tool_call_history"].append(ToolCallHistoryEntry(
            tool_name=tool_name,
            args_hash=args_hash,
            tool_call_id=tool_call_id,
            result_hash=result_hash,
        ))
    if len(state["tool_call_history"]) > resolved.history_size:
        state["tool_call_history"] = state["tool_call_history"][-resolved.history_size:]


def get_tool_call_stats(state: dict[str, Any]) -> dict[str, Any]:
    """Get tool call statistics for debugging/monitoring."""
    history: list[ToolCallHistoryEntry] = state.get("tool_call_history", [])
    patterns: dict[str, dict[str, Any]] = {}
    for call in history:
        if call.args_hash in patterns:
            patterns[call.args_hash]["count"] += 1
        else:
            patterns[call.args_hash] = {"tool_name": call.tool_name, "count": 1}

    most_frequent = None
    for pattern in patterns.values():
        if most_frequent is None or pattern["count"] > most_frequent["count"]:
            most_frequent = pattern

    return {
        "total_calls": len(history),
        "unique_patterns": len(patterns),
        "most_frequent": most_frequent,
    }
