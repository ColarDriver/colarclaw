"""Tool call loop detection — ported from bk/src/agents/tool-loop-detection.ts.

Detects repetitive tool call patterns:
- generic_repeat: same tool+args called repeatedly
- known_poll_no_progress: polling tool with identical results
- global_circuit_breaker: absolute safety limit
- ping_pong: alternating between two tool calls with no progress
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal

log = logging.getLogger("openclaw.tools.loop_detection")

# ── Constants ──────────────────────────────────────────────────────────────
TOOL_CALL_HISTORY_SIZE = 30
WARNING_THRESHOLD = 10
CRITICAL_THRESHOLD = 20
GLOBAL_CIRCUIT_BREAKER_THRESHOLD = 30

LoopDetectorKind = Literal[
    "generic_repeat",
    "known_poll_no_progress",
    "global_circuit_breaker",
    "ping_pong",
]


# ── Types ──────────────────────────────────────────────────────────────────

@dataclass
class LoopDetectionConfig:
    enabled: bool = False
    history_size: int = TOOL_CALL_HISTORY_SIZE
    warning_threshold: int = WARNING_THRESHOLD
    critical_threshold: int = CRITICAL_THRESHOLD
    global_circuit_breaker_threshold: int = GLOBAL_CIRCUIT_BREAKER_THRESHOLD
    detector_generic_repeat: bool = True
    detector_known_poll_no_progress: bool = True
    detector_ping_pong: bool = True


@dataclass
class LoopDetectionResult:
    stuck: bool = False
    level: Literal["warning", "critical"] | None = None
    detector: LoopDetectorKind | None = None
    count: int = 0
    message: str = ""
    paired_tool_name: str | None = None
    warning_key: str | None = None


@dataclass
class ToolCallRecord:
    tool_name: str
    args_hash: str
    tool_call_id: str | None = None
    result_hash: str | None = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class ToolCallHistoryState:
    """Tracks tool call history for loop detection within a session/run."""
    tool_call_history: list[ToolCallRecord] = field(default_factory=list)


# ── Helpers ────────────────────────────────────────────────────────────────

def _as_positive_int(value: int | None, fallback: int) -> int:
    if value is None or not isinstance(value, int) or value <= 0:
        return fallback
    return value


def _resolve_config(config: LoopDetectionConfig | None) -> LoopDetectionConfig:
    if config is None:
        return LoopDetectionConfig()

    warning = _as_positive_int(config.warning_threshold, WARNING_THRESHOLD)
    critical = _as_positive_int(config.critical_threshold, CRITICAL_THRESHOLD)
    circuit_breaker = _as_positive_int(
        config.global_circuit_breaker_threshold, GLOBAL_CIRCUIT_BREAKER_THRESHOLD
    )

    if critical <= warning:
        critical = warning + 1
    if circuit_breaker <= critical:
        circuit_breaker = critical + 1

    return LoopDetectionConfig(
        enabled=config.enabled,
        history_size=_as_positive_int(config.history_size, TOOL_CALL_HISTORY_SIZE),
        warning_threshold=warning,
        critical_threshold=critical,
        global_circuit_breaker_threshold=circuit_breaker,
        detector_generic_repeat=config.detector_generic_repeat,
        detector_known_poll_no_progress=config.detector_known_poll_no_progress,
        detector_ping_pong=config.detector_ping_pong,
    )


def _stable_stringify(value: Any) -> str:
    """Deterministic JSON-like serialization for hash stability."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return json.dumps(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ",".join(_stable_stringify(item) for item in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value.keys())
        pairs = ",".join(
            f"{json.dumps(k)}:{_stable_stringify(value[k])}" for k in keys
        )
        return "{" + pairs + "}"
    return json.dumps(str(value))


def _digest_stable(value: Any) -> str:
    try:
        serialized = _stable_stringify(value)
    except Exception:
        serialized = str(value)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def hash_tool_call(tool_name: str, params: Any) -> str:
    """Hash a tool call for pattern matching (tool name + stable digest of params)."""
    return f"{tool_name}:{_digest_stable(params)}"


def _is_known_poll_tool(tool_name: str, params: Any) -> bool:
    if tool_name == "command_status":
        return True
    if tool_name != "process" or not isinstance(params, dict):
        return False
    action = params.get("action")
    return action in ("poll", "log")


def _extract_text_content(result: Any) -> str:
    if not isinstance(result, dict) or not isinstance(result.get("content"), list):
        return ""
    parts: list[str] = []
    for entry in result["content"]:
        if (
            isinstance(entry, dict)
            and isinstance(entry.get("type"), str)
            and isinstance(entry.get("text"), str)
        ):
            parts.append(entry["text"])
    return "\n".join(parts).strip()


def _format_error_for_hash(error: Any) -> str:
    if isinstance(error, Exception):
        return str(error) or type(error).__name__
    if isinstance(error, str):
        return error
    return _stable_stringify(error)


def _hash_tool_outcome(
    tool_name: str,
    params: Any,
    result: Any,
    error: Any,
) -> str | None:
    if error is not None:
        return f"error:{_digest_stable(_format_error_for_hash(error))}"
    if not isinstance(result, dict):
        return None if result is None else _digest_stable(result)

    details = result.get("details", {})
    if not isinstance(details, dict):
        details = {}
    text = _extract_text_content(result)

    if _is_known_poll_tool(tool_name, params) and tool_name == "process" and isinstance(params, dict):
        action = params.get("action")
        if action == "poll":
            return _digest_stable({
                "action": action,
                "status": details.get("status"),
                "exitCode": details.get("exitCode"),
                "exitSignal": details.get("exitSignal"),
                "aggregated": details.get("aggregated"),
                "text": text,
            })
        if action == "log":
            return _digest_stable({
                "action": action,
                "status": details.get("status"),
                "totalLines": details.get("totalLines"),
                "totalChars": details.get("totalChars"),
                "truncated": details.get("truncated"),
                "exitCode": details.get("exitCode"),
                "exitSignal": details.get("exitSignal"),
                "text": text,
            })

    return _digest_stable({"details": details, "text": text})


def _no_progress_streak(
    history: list[ToolCallRecord],
    tool_name: str,
    args_hash: str,
) -> tuple[int, str | None]:
    """Count consecutive identical-result calls for the same tool+args at tail of history."""
    streak = 0
    latest_result_hash: str | None = None

    for record in reversed(history):
        if record.tool_name != tool_name or record.args_hash != args_hash:
            continue
        if not record.result_hash:
            continue
        if latest_result_hash is None:
            latest_result_hash = record.result_hash
            streak = 1
            continue
        if record.result_hash != latest_result_hash:
            break
        streak += 1

    return streak, latest_result_hash


def _ping_pong_streak(
    history: list[ToolCallRecord],
    current_signature: str,
) -> tuple[int, str | None, str | None, bool]:
    """Detect alternating tool-call patterns (A-B-A-B...)."""
    if not history:
        return 0, None, None, False

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
        return 0, None, None, False

    alternating_tail_count = 0
    for i in range(len(history) - 1, -1, -1):
        call = history[i]
        expected = last.args_hash if alternating_tail_count % 2 == 0 else other_signature
        if call.args_hash != expected:
            break
        alternating_tail_count += 1

    if alternating_tail_count < 2:
        return 0, None, None, False

    if current_signature != other_signature:
        return 0, None, None, False

    # Check for no-progress evidence
    tail_start = max(0, len(history) - alternating_tail_count)
    first_hash_a: str | None = None
    first_hash_b: str | None = None
    no_progress_evidence = True

    for i in range(tail_start, len(history)):
        call = history[i]
        if not call.result_hash:
            no_progress_evidence = False
            break
        if call.args_hash == last.args_hash:
            if first_hash_a is None:
                first_hash_a = call.result_hash
            elif first_hash_a != call.result_hash:
                no_progress_evidence = False
                break
        elif call.args_hash == other_signature:
            if first_hash_b is None:
                first_hash_b = call.result_hash
            elif first_hash_b != call.result_hash:
                no_progress_evidence = False
                break
        else:
            no_progress_evidence = False
            break

    if not first_hash_a or not first_hash_b:
        no_progress_evidence = False

    return (
        alternating_tail_count + 1,
        last.tool_name,
        last.args_hash,
        no_progress_evidence,
    )


def _canonical_pair_key(sig_a: str, sig_b: str) -> str:
    parts = sorted([sig_a, sig_b])
    return "|".join(parts)


# ── Public API ─────────────────────────────────────────────────────────────

NOT_STUCK = LoopDetectionResult(stuck=False)


def detect_tool_call_loop(
    state: ToolCallHistoryState,
    tool_name: str,
    params: Any,
    config: LoopDetectionConfig | None = None,
) -> LoopDetectionResult:
    """Detect if an agent is stuck in a repetitive tool call loop."""
    resolved = _resolve_config(config)
    if not resolved.enabled:
        return NOT_STUCK

    history = state.tool_call_history
    current_hash = hash_tool_call(tool_name, params)
    no_progress_count, latest_result_hash = _no_progress_streak(history, tool_name, current_hash)
    known_poll = _is_known_poll_tool(tool_name, params)
    pp_count, pp_paired_tool, pp_paired_sig, pp_no_progress = _ping_pong_streak(history, current_hash)

    # Global circuit breaker
    if no_progress_count >= resolved.global_circuit_breaker_threshold:
        log.error(
            "Global circuit breaker triggered: %s repeated %d times with no progress",
            tool_name, no_progress_count,
        )
        return LoopDetectionResult(
            stuck=True,
            level="critical",
            detector="global_circuit_breaker",
            count=no_progress_count,
            message=(
                f"CRITICAL: {tool_name} has repeated identical no-progress outcomes "
                f"{no_progress_count} times. Session execution blocked by global "
                f"circuit breaker to prevent runaway loops."
            ),
            warning_key=f"global:{tool_name}:{current_hash}:{latest_result_hash or 'none'}",
        )

    # Known poll no-progress — critical
    if (
        known_poll
        and resolved.detector_known_poll_no_progress
        and no_progress_count >= resolved.critical_threshold
    ):
        log.error("Critical polling loop detected: %s repeated %d times", tool_name, no_progress_count)
        return LoopDetectionResult(
            stuck=True,
            level="critical",
            detector="known_poll_no_progress",
            count=no_progress_count,
            message=(
                f"CRITICAL: Called {tool_name} with identical arguments and no progress "
                f"{no_progress_count} times. This appears to be a stuck polling loop. "
                f"Session execution blocked to prevent resource waste."
            ),
            warning_key=f"poll:{tool_name}:{current_hash}:{latest_result_hash or 'none'}",
        )

    # Known poll no-progress — warning
    if (
        known_poll
        and resolved.detector_known_poll_no_progress
        and no_progress_count >= resolved.warning_threshold
    ):
        log.warning("Polling loop warning: %s repeated %d times", tool_name, no_progress_count)
        return LoopDetectionResult(
            stuck=True,
            level="warning",
            detector="known_poll_no_progress",
            count=no_progress_count,
            message=(
                f"WARNING: You have called {tool_name} {no_progress_count} times with "
                f"identical arguments and no progress. Stop polling and either "
                f"(1) increase wait time between checks, or (2) report the task as "
                f"failed if the process is stuck."
            ),
            warning_key=f"poll:{tool_name}:{current_hash}:{latest_result_hash or 'none'}",
        )

    # Ping-pong — critical
    pp_warning_key = (
        f"pingpong:{_canonical_pair_key(current_hash, pp_paired_sig)}"
        if pp_paired_sig
        else f"pingpong:{tool_name}:{current_hash}"
    )

    if (
        resolved.detector_ping_pong
        and pp_count >= resolved.critical_threshold
        and pp_no_progress
    ):
        log.error(
            "Critical ping-pong loop detected: alternating calls count=%d currentTool=%s",
            pp_count, tool_name,
        )
        return LoopDetectionResult(
            stuck=True,
            level="critical",
            detector="ping_pong",
            count=pp_count,
            message=(
                f"CRITICAL: You are alternating between repeated tool-call patterns "
                f"({pp_count} consecutive calls) with no progress. This appears to be "
                f"a stuck ping-pong loop. Session execution blocked to prevent resource waste."
            ),
            paired_tool_name=pp_paired_tool,
            warning_key=pp_warning_key,
        )

    # Ping-pong — warning
    if resolved.detector_ping_pong and pp_count >= resolved.warning_threshold:
        log.warning(
            "Ping-pong loop warning: alternating calls count=%d currentTool=%s",
            pp_count, tool_name,
        )
        return LoopDetectionResult(
            stuck=True,
            level="warning",
            detector="ping_pong",
            count=pp_count,
            message=(
                f"WARNING: You are alternating between repeated tool-call patterns "
                f"({pp_count} consecutive calls). This looks like a ping-pong loop; "
                f"stop retrying and report the task as failed."
            ),
            paired_tool_name=pp_paired_tool,
            warning_key=pp_warning_key,
        )

    # Generic repeat — warning
    recent_count = sum(
        1 for h in history
        if h.tool_name == tool_name and h.args_hash == current_hash
    )
    if (
        not known_poll
        and resolved.detector_generic_repeat
        and recent_count >= resolved.warning_threshold
    ):
        log.warning(
            "Loop warning: %s called %d times with identical arguments",
            tool_name, recent_count,
        )
        return LoopDetectionResult(
            stuck=True,
            level="warning",
            detector="generic_repeat",
            count=recent_count,
            message=(
                f"WARNING: You have called {tool_name} {recent_count} times with "
                f"identical arguments. If this is not making progress, stop retrying "
                f"and report the task as failed."
            ),
            warning_key=f"generic:{tool_name}:{current_hash}",
        )

    return NOT_STUCK


def record_tool_call(
    state: ToolCallHistoryState,
    tool_name: str,
    params: Any,
    tool_call_id: str | None = None,
    config: LoopDetectionConfig | None = None,
) -> None:
    """Record a tool call in the session's history for loop detection."""
    resolved = _resolve_config(config)

    state.tool_call_history.append(
        ToolCallRecord(
            tool_name=tool_name,
            args_hash=hash_tool_call(tool_name, params),
            tool_call_id=tool_call_id,
        )
    )

    if len(state.tool_call_history) > resolved.history_size:
        state.tool_call_history.pop(0)


def record_tool_call_outcome(
    state: ToolCallHistoryState,
    tool_name: str,
    tool_params: Any,
    tool_call_id: str | None = None,
    result: Any = None,
    error: Any = None,
    config: LoopDetectionConfig | None = None,
) -> None:
    """Record a completed tool call outcome for no-progress detection."""
    resolved = _resolve_config(config)
    result_hash = _hash_tool_outcome(tool_name, tool_params, result, error)
    if not result_hash:
        return

    args_hash = hash_tool_call(tool_name, tool_params)
    matched = False

    for i in range(len(state.tool_call_history) - 1, -1, -1):
        call = state.tool_call_history[i]
        if tool_call_id and call.tool_call_id != tool_call_id:
            continue
        if call.tool_name != tool_name or call.args_hash != args_hash:
            continue
        if call.result_hash is not None:
            continue
        call.result_hash = result_hash
        matched = True
        break

    if not matched:
        state.tool_call_history.append(
            ToolCallRecord(
                tool_name=tool_name,
                args_hash=args_hash,
                tool_call_id=tool_call_id,
                result_hash=result_hash,
            )
        )

    if len(state.tool_call_history) > resolved.history_size:
        excess = len(state.tool_call_history) - resolved.history_size
        state.tool_call_history = state.tool_call_history[excess:]


def get_tool_call_stats(
    state: ToolCallHistoryState,
) -> dict[str, Any]:
    """Get current tool call statistics for debugging/monitoring."""
    history = state.tool_call_history
    patterns: dict[str, dict[str, Any]] = {}

    for call in history:
        key = call.args_hash
        if key in patterns:
            patterns[key]["count"] += 1
        else:
            patterns[key] = {"tool_name": call.tool_name, "count": 1}

    most_frequent: dict[str, Any] | None = None
    for pattern in patterns.values():
        if most_frequent is None or pattern["count"] > most_frequent["count"]:
            most_frequent = pattern

    return {
        "total_calls": len(history),
        "unique_patterns": len(patterns),
        "most_frequent": most_frequent,
    }
