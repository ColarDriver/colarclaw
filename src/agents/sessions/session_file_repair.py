"""Session file repair — ported from bk/src/agents/session-file-repair.ts."""
from __future__ import annotations
import json
import logging
import os
from typing import Any

log = logging.getLogger("openclaw.agents.session_file_repair")

def repair_session_file(file_path: str) -> dict[str, Any]:
    """Repair a corrupted JSONL session file by removing invalid lines."""
    if not os.path.isfile(file_path):
        return {"repaired": False, "error": "file not found"}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        return {"repaired": False, "error": str(e)}
    valid_lines: list[str] = []
    invalid_count = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            json.loads(stripped)
            valid_lines.append(stripped + "\n")
        except json.JSONDecodeError:
            invalid_count += 1
    if invalid_count == 0:
        return {"repaired": False, "valid_lines": len(valid_lines)}
    try:
        tmp_path = f"{file_path}.repair.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.writelines(valid_lines)
        os.replace(tmp_path, file_path)
        log.info("Repaired %s: removed %d invalid lines", file_path, invalid_count)
        return {"repaired": True, "valid_lines": len(valid_lines), "removed": invalid_count}
    except Exception as e:
        return {"repaired": False, "error": str(e)}
