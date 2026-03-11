from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
import os
import re
from pathlib import Path


@dataclass(frozen=True)
class TemporalDecayConfig:
    enabled: bool = False
    half_life_days: float = 30.0


_date_file_pattern = re.compile(r"^memory/(\d{4})-(\d{2})-(\d{2})\.md$", flags=re.IGNORECASE)


def _is_evergreen(path: str) -> bool:
    lowered = path.lower()
    return lowered in {'memory.md', 'memory/memory.md'} or lowered.startswith('memory/topics/')


def _extract_timestamp(path: str, workspace_dir: str, now_ms: float) -> float:
    match = _date_file_pattern.match(path)
    if match:
        year, month, day = match.groups()
        try:
            dt = datetime(int(year), int(month), int(day))
            return dt.timestamp() * 1000.0
        except Exception:
            pass

    full_path = Path(workspace_dir) / path
    try:
        return os.path.getmtime(full_path) * 1000.0
    except Exception:
        return now_ms


def apply_temporal_decay(
    *,
    results: list[dict[str, object]],
    workspace_dir: str,
    config: TemporalDecayConfig,
    now_ms: float | None = None,
) -> list[dict[str, object]]:
    if not config.enabled:
        return results

    now = now_ms if now_ms is not None else datetime.utcnow().timestamp() * 1000.0
    half_life_ms = max(1.0, config.half_life_days) * 24 * 60 * 60 * 1000.0

    output: list[dict[str, object]] = []
    for item in results:
        path = str(item.get('path', ''))
        score = float(item.get('score', 0.0))
        if _is_evergreen(path):
            output.append(item)
            continue

        ts = _extract_timestamp(path, workspace_dir, now)
        age_ms = max(0.0, now - ts)
        decay = 0.5 ** (age_ms / half_life_ms)
        updated = dict(item)
        updated['score'] = score * decay
        output.append(updated)

    output.sort(key=lambda entry: float(entry.get('score', 0.0)), reverse=True)
    return output
