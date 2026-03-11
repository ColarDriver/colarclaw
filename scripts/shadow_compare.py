#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def read_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def normalize_answer(payload: dict[str, object]) -> str:
    text = payload.get("text")
    return str(text).strip() if isinstance(text, str) else ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare legacy and new shadow run outputs")
    parser.add_argument("--legacy", required=True)
    parser.add_argument("--candidate", required=True)
    args = parser.parse_args()

    legacy = read_jsonl(Path(args.legacy))
    candidate = read_jsonl(Path(args.candidate))
    total = min(len(legacy), len(candidate))
    same = 0
    for idx in range(total):
        if normalize_answer(legacy[idx]) == normalize_answer(candidate[idx]):
            same += 1
    ratio = (same / total) if total else 0.0
    print(json.dumps({"total": total, "exactMatch": same, "ratio": ratio}, ensure_ascii=False))


if __name__ == "__main__":
    main()
