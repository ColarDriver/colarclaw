#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: Path) -> list[dict[str, object]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("validation input must be a JSON array")
    return [item for item in raw if isinstance(item, dict)]


def summarize(rows: list[dict[str, object]]) -> dict[str, int]:
    sessions = 0
    messages = 0
    for row in rows:
        row_type = row.get("type")
        if row_type == "session":
            sessions += 1
        elif row_type == "message":
            messages += 1
    return {"sessions": sessions, "messages": messages}


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate migration output cardinality")
    parser.add_argument("--source", required=True, help="Source transformed JSON")
    parser.add_argument("--expected-sessions", type=int, required=True)
    parser.add_argument("--expected-messages", type=int, required=True)
    args = parser.parse_args()

    rows = load(Path(args.source))
    summary = summarize(rows)
    if summary["sessions"] != args.expected_sessions:
        raise SystemExit(f"session mismatch: got={summary['sessions']} expected={args.expected_sessions}")
    if summary["messages"] != args.expected_messages:
        raise SystemExit(f"message mismatch: got={summary['messages']} expected={args.expected_messages}")
    print("Migration validation passed", summary)


if __name__ == "__main__":
    main()
