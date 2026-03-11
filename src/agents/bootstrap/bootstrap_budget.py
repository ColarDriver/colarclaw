"""Bootstrap budget analysis — ported from bk/src/agents/bootstrap-budget.ts.

Tracks how much of the bootstrap context files are injected vs truncated,
analyses budget consumption, and generates truncation warnings.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

DEFAULT_BOOTSTRAP_NEAR_LIMIT_RATIO = 0.85
DEFAULT_BOOTSTRAP_PROMPT_WARNING_MAX_FILES = 3
DEFAULT_BOOTSTRAP_PROMPT_WARNING_SIGNATURE_HISTORY_MAX = 32

BootstrapTruncationCause = str  # "per-file-limit" | "total-limit"
BootstrapPromptWarningMode = str  # "off" | "once" | "always"


@dataclass
class BootstrapInjectionStat:
    name: str
    path: str
    missing: bool
    raw_chars: int
    injected_chars: int
    truncated: bool


@dataclass
class BootstrapAnalyzedFile:
    name: str
    path: str
    missing: bool
    raw_chars: int
    injected_chars: int
    truncated: bool
    near_limit: bool
    causes: list[str]


@dataclass
class BootstrapBudgetAnalysis:
    files: list[BootstrapAnalyzedFile]
    truncated_files: list[BootstrapAnalyzedFile]
    near_limit_files: list[BootstrapAnalyzedFile]
    total_near_limit: bool
    has_truncation: bool
    totals: dict[str, Any]


@dataclass
class BootstrapPromptWarning:
    signature: str | None = None
    warning_shown: bool = False
    lines: list[str] = field(default_factory=list)
    warning_signatures_seen: list[str] = field(default_factory=list)


def _normalize_positive_limit(value: float | int) -> int:
    import math
    if not math.isfinite(value) or value <= 0:
        return 1
    return int(value)


def _format_warning_cause(cause: str) -> str:
    return "max/file" if cause == "per-file-limit" else "max/total"


def _normalize_seen_signatures(signatures: list[str] | None) -> list[str]:
    if not signatures:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for sig in signatures:
        value = sig.strip() if isinstance(sig, str) else ""
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _append_seen_signature(signatures: list[str], signature: str) -> list[str]:
    if not signature.strip():
        return signatures
    if signature in signatures:
        return signatures
    result = signatures + [signature]
    if len(result) <= DEFAULT_BOOTSTRAP_PROMPT_WARNING_SIGNATURE_HISTORY_MAX:
        return result
    return result[-DEFAULT_BOOTSTRAP_PROMPT_WARNING_SIGNATURE_HISTORY_MAX:]


def build_bootstrap_injection_stats(
    bootstrap_files: list[Any],
    injected_files: list[Any],
) -> list[BootstrapInjectionStat]:
    """Build injection statistics by matching bootstrap files with injected context."""
    injected_by_path: dict[str, str] = {}
    injected_by_basename: dict[str, str] = {}

    for f in injected_files:
        path_value = getattr(f, "path", "") if hasattr(f, "path") else f.get("path", "")
        content = getattr(f, "content", "") if hasattr(f, "content") else f.get("content", "")
        path_val = path_value.strip() if isinstance(path_value, str) else ""
        if not path_val:
            continue
        if path_val not in injected_by_path:
            injected_by_path[path_val] = content
        base = os.path.basename(path_val.replace("\\", "/"))
        if base not in injected_by_basename:
            injected_by_basename[base] = content

    stats: list[BootstrapInjectionStat] = []
    for bf in bootstrap_files:
        name = getattr(bf, "name", "") if hasattr(bf, "name") else bf.get("name", "")
        path_val = getattr(bf, "path", "") if hasattr(bf, "path") else bf.get("path", "")
        missing = getattr(bf, "missing", False) if hasattr(bf, "missing") else bf.get("missing", False)
        content = getattr(bf, "content", "") if hasattr(bf, "content") else bf.get("content", "")

        path_str = path_val.strip() if isinstance(path_val, str) else ""
        raw_chars = 0 if missing else len((content or "").rstrip())

        injected = (
            injected_by_path.get(path_str)
            or injected_by_path.get(name)
            or injected_by_basename.get(name)
        )
        injected_chars = len(injected) if injected else 0
        truncated = not missing and injected_chars < raw_chars

        stats.append(BootstrapInjectionStat(
            name=name,
            path=path_str or name,
            missing=missing,
            raw_chars=raw_chars,
            injected_chars=injected_chars,
            truncated=truncated,
        ))
    return stats


def analyze_bootstrap_budget(
    files: list[BootstrapInjectionStat],
    bootstrap_max_chars: int,
    bootstrap_total_max_chars: int,
    near_limit_ratio: float | None = None,
) -> BootstrapBudgetAnalysis:
    """Analyze bootstrap context budget consumption."""
    max_chars = _normalize_positive_limit(bootstrap_max_chars)
    total_max = _normalize_positive_limit(bootstrap_total_max_chars)

    import math
    if (
        near_limit_ratio is None
        or not isinstance(near_limit_ratio, (int, float))
        or not math.isfinite(near_limit_ratio)
        or near_limit_ratio <= 0
        or near_limit_ratio >= 1
    ):
        ratio = DEFAULT_BOOTSTRAP_NEAR_LIMIT_RATIO
    else:
        ratio = near_limit_ratio

    non_missing = [f for f in files if not f.missing]
    raw_total = sum(f.raw_chars for f in non_missing)
    injected_total = sum(f.injected_chars for f in non_missing)
    total_near_limit = injected_total >= int(total_max * ratio + 0.5)
    total_over_limit = injected_total >= total_max

    analyzed: list[BootstrapAnalyzedFile] = []
    for f in files:
        if f.missing:
            analyzed.append(BootstrapAnalyzedFile(
                name=f.name, path=f.path, missing=True,
                raw_chars=0, injected_chars=0, truncated=False,
                near_limit=False, causes=[],
            ))
            continue
        per_file_over = f.raw_chars > max_chars
        near = f.raw_chars >= int(max_chars * ratio + 0.5)
        causes: list[str] = []
        if f.truncated:
            if per_file_over:
                causes.append("per-file-limit")
            if total_over_limit:
                causes.append("total-limit")
        analyzed.append(BootstrapAnalyzedFile(
            name=f.name, path=f.path, missing=False,
            raw_chars=f.raw_chars, injected_chars=f.injected_chars,
            truncated=f.truncated, near_limit=near, causes=causes,
        ))

    truncated_files = [f for f in analyzed if f.truncated]
    near_limit_files = [f for f in analyzed if f.near_limit]

    return BootstrapBudgetAnalysis(
        files=analyzed,
        truncated_files=truncated_files,
        near_limit_files=near_limit_files,
        total_near_limit=total_near_limit,
        has_truncation=len(truncated_files) > 0,
        totals={
            "rawChars": raw_total,
            "injectedChars": injected_total,
            "truncatedChars": max(0, raw_total - injected_total),
            "bootstrapMaxChars": max_chars,
            "bootstrapTotalMaxChars": total_max,
            "nearLimitRatio": ratio,
        },
    )


def build_bootstrap_truncation_signature(analysis: BootstrapBudgetAnalysis) -> str | None:
    """Build a deterministic signature of which files were truncated and why."""
    if not analysis.has_truncation:
        return None
    file_data = sorted(
        [
            {
                "path": f.path or f.name,
                "rawChars": f.raw_chars,
                "injectedChars": f.injected_chars,
                "causes": sorted(f.causes),
            }
            for f in analysis.truncated_files
        ],
        key=lambda d: (d["path"], d["rawChars"], d["injectedChars"], "+".join(d["causes"])),
    )
    return json.dumps({
        "bootstrapMaxChars": analysis.totals["bootstrapMaxChars"],
        "bootstrapTotalMaxChars": analysis.totals["bootstrapTotalMaxChars"],
        "files": file_data,
    })


def format_bootstrap_truncation_warning_lines(
    analysis: BootstrapBudgetAnalysis,
    max_files: int | None = None,
) -> list[str]:
    """Format human-readable truncation warning lines."""
    if not analysis.has_truncation:
        return []

    import math
    if max_files is None or not isinstance(max_files, (int, float)) or not math.isfinite(max_files) or max_files <= 0:
        max_display = DEFAULT_BOOTSTRAP_PROMPT_WARNING_MAX_FILES
    else:
        max_display = int(max_files)

    lines: list[str] = []
    name_counts: dict[str, int] = {}
    for f in analysis.truncated_files:
        name_counts[f.name] = name_counts.get(f.name, 0) + 1

    top_files = analysis.truncated_files[:max_display]
    for f in top_files:
        pct = round(((f.raw_chars - f.injected_chars) / f.raw_chars) * 100) if f.raw_chars > 0 else 0
        cause_text = ", ".join(_format_warning_cause(c) for c in f.causes) if f.causes else ""
        name_label = (
            f"{f.name} ({f.path})"
            if name_counts.get(f.name, 0) > 1 and f.path.strip()
            else f.name
        )
        lines.append(
            f"{name_label}: {f.raw_chars} raw -> {f.injected_chars} injected "
            f"(~{max(0, pct)}% removed{'; ' + cause_text if cause_text else ''})."
        )

    remaining = len(analysis.truncated_files) - len(top_files)
    if remaining > 0:
        lines.append(f"+{remaining} more truncated file(s).")

    lines.append(
        "If unintentional, raise agents.defaults.bootstrapMaxChars "
        "and/or agents.defaults.bootstrapTotalMaxChars."
    )
    return lines


def build_bootstrap_prompt_warning(
    analysis: BootstrapBudgetAnalysis,
    mode: str = "off",
    previous_signature: str | None = None,
    seen_signatures: list[str] | None = None,
    max_files: int | None = None,
) -> BootstrapPromptWarning:
    """Build prompt warning for bootstrap truncation."""
    signature = build_bootstrap_truncation_signature(analysis)
    sigs = _normalize_seen_signatures(seen_signatures)
    if previous_signature and previous_signature not in sigs:
        sigs = _append_seen_signature(sigs, previous_signature)

    has_seen = bool(signature and signature in sigs)
    warning_shown = mode != "off" and bool(signature) and (mode == "always" or not has_seen)
    warning_sigs = _append_seen_signature(sigs, signature) if signature and mode != "off" else sigs

    return BootstrapPromptWarning(
        signature=signature,
        warning_shown=warning_shown,
        lines=(
            format_bootstrap_truncation_warning_lines(analysis, max_files)
            if warning_shown
            else []
        ),
        warning_signatures_seen=warning_sigs,
    )
